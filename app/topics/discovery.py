"""Topic discovery.

Walks every catalogue level (country → city → attraction → category → collection →
product), crosses it with the market's intent clusters, scores the result and stores
deduplicated candidates.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings, get_settings
from app.db.enums import EntityType, TopicStatus
from app.db.models import (
    Attraction,
    Category,
    City,
    Collection,
    Country,
    Product,
    QueryCandidate,
    TopicCandidate,
)
from app.db.types import utcnow
from app.logging_setup import get_logger, job_context
from app.topics.clusters import ClusterDefinition, KeywordClusterRegistry
from app.topics.dedup import DeduplicationService, canonicalize_query, topic_key, topic_slug
from app.topics.demand import SearchDemandProvider, build_demand_provider
from app.topics.morphology import render_pattern
from app.topics.scoring import (
    ScoreInputs,
    commercial_relevance_signal,
    product_quality_signal,
    score_topic,
)

log = get_logger("topics.discovery")

#: Intents whose searcher is close to buying — used for the commercial signal.
COMMERCIAL_INTENTS = {
    "audio_guide",
    "tickets",
    "ticket_with_audio",
    "self_guided_tour",
    "self_guided_in_city",
    "self_guided_routes",
    "walking_tour",
    "walking_route",
    "independent_trip",
    "themed_walking_tour",
    "best_in_city",
}


@dataclass(slots=True)
class DiscoveryStats:
    examined: int = 0
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    thin: int = 0
    by_entity_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def as_dict(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "created": self.created,
            "updated": self.updated,
            "duplicates": self.duplicates,
            "thin": self.thin,
            "by_entity_type": dict(self.by_entity_type),
        }


@dataclass(slots=True)
class EntityRef:
    entity_type: str
    external_id: str
    name: str
    slug: str
    popularity: float
    product_ids: list[str]
    #: Extra placeholder values for the pattern renderer (city, country, theme, …).
    context: dict[str, str] = field(default_factory=dict)


class CatalogIndex:
    """In-memory view of one market's catalogue used by discovery and ranking."""

    def __init__(self, session: Session, market: Market) -> None:
        self.market = market
        self.products: list[Product] = list(
            session.scalars(
                select(Product).where(Product.market == market, Product.available.is_(True))
            ).all()
        )
        self.products_by_id = {p.external_id: p for p in self.products}
        self.cities = {
            c.external_id: c
            for c in session.scalars(select(City).where(City.market == market)).all()
        }
        self.countries = {
            c.external_id: c
            for c in session.scalars(select(Country).where(Country.market == market)).all()
        }
        self.attractions = {
            a.external_id: a
            for a in session.scalars(select(Attraction).where(Attraction.market == market)).all()
        }
        self.categories = {
            c.external_id: c
            for c in session.scalars(select(Category).where(Category.market == market)).all()
        }
        self.collections = {
            c.external_id: c
            for c in session.scalars(select(Collection).where(Collection.market == market)).all()
        }

        self.by_city: dict[str, list[str]] = defaultdict(list)
        self.by_country: dict[str, list[str]] = defaultdict(list)
        self.by_attraction: dict[str, list[str]] = defaultdict(list)
        self.by_category_city: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.by_collection_city: dict[tuple[str, str], list[str]] = defaultdict(list)

        for product in self.products:
            if product.city_external_id:
                self.by_city[product.city_external_id].append(product.external_id)
            if product.country_external_id:
                self.by_country[product.country_external_id].append(product.external_id)
            for attraction_link in product.attractions:
                self.by_attraction[attraction_link.attraction_external_id].append(
                    product.external_id
                )
            if product.city_external_id:
                for category_link in product.categories:
                    self.by_category_city[
                        (category_link.category_external_id, product.city_external_id)
                    ].append(product.external_id)
                for collection_link in product.collections:
                    self.by_collection_city[
                        (collection_link.collection_external_id, product.city_external_id)
                    ].append(product.external_id)

        self._max_rank = max((p.popularity_rank or 0 for p in self.products), default=1) or 1

    def popularity_from_rank(self, rank: int | None, total: int) -> float:
        if rank is None or total <= 1:
            return 0.4
        return max(0.0, 1.0 - rank / total)

    def product_popularity(self, product_ids: list[str]) -> float:
        ranks = [
            rank
            for pid in product_ids
            if pid in self.products_by_id
            and (rank := self.products_by_id[pid].popularity_rank) is not None
        ]
        if not ranks:
            return 0.3
        best = min(ranks)
        return max(0.0, 1.0 - best / max(self._max_rank, 1))

    def freshness(self, product_ids: list[str], *, now: dt.datetime | None = None) -> float:
        now = now or utcnow()
        stamps = [
            self.products_by_id[pid].created_at for pid in product_ids if pid in self.products_by_id
        ]
        if not stamps:
            return 0.2
        newest = max(stamps)
        age_days = max(0.0, (now - newest).total_seconds() / 86400)
        return max(0.0, 1.0 - age_days / 60.0)


class TopicDiscoveryService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        demand_provider: SearchDemandProvider | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.registry = KeywordClusterRegistry(session)
        self.dedup = DeduplicationService(session, self.settings)
        self.demand = demand_provider or build_demand_provider(self.settings)
        #: Canonical queries already staged in this session but not yet flushed.
        self._seen_queries: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------ main
    def discover(self, market: Market, *, limit: int | None = None) -> DiscoveryStats:
        limit = limit or self.settings.topic_candidates_per_run
        stats = DiscoveryStats()
        with job_context("topics.discover", market=market):
            index = CatalogIndex(self.session, market)
            diversity = self._diversity_baseline(market)

            # Round-robin across catalogue levels so a deep city catalogue cannot
            # starve country, category, collection and product topics.
            streams = {
                entity_type: self._stream(market, index, entity_type)
                for entity_type in (
                    EntityType.COUNTRY,
                    EntityType.CITY,
                    EntityType.ATTRACTION,
                    EntityType.CATEGORY,
                    EntityType.COLLECTION,
                    EntityType.PRODUCT,
                )
            }
            while streams and stats.created + stats.updated < limit:
                for entity_type in list(streams):
                    if stats.created + stats.updated >= limit:
                        break
                    try:
                        entity, cluster = next(streams[entity_type])
                    except StopIteration:
                        del streams[entity_type]
                        continue
                    stats.examined += 1
                    self._consider(market, index, entity, cluster, stats, diversity)
            self.session.flush()
        return stats

    def _stream(self, market: Market, index: CatalogIndex, entity_type: str):
        clusters = self.registry.for_entity_type(market, entity_type)
        if not clusters:
            return
        for entity in self._iter_entities(index, only=entity_type):
            for cluster in clusters:
                yield entity, cluster

    # -------------------------------------------------------------- entities
    def _iter_entities(self, index: CatalogIndex, *, only: str | None = None):
        if only in (None, EntityType.COUNTRY):
            yield from self._countries(index)
        if only in (None, EntityType.CITY):
            yield from self._cities(index)
        if only in (None, EntityType.ATTRACTION):
            yield from self._attractions(index)
        if only in (None, EntityType.CATEGORY):
            yield from self._categories(index)
        if only in (None, EntityType.COLLECTION):
            yield from self._collections(index)
        if only in (None, EntityType.PRODUCT):
            yield from self._products(index)

    def _countries(self, index: CatalogIndex):
        total_countries = max(len(index.countries), 1)
        for country in sorted(index.countries.values(), key=lambda c: -(c.product_count or 0)):
            product_ids = index.by_country.get(country.external_id, [])
            if not product_ids:
                continue
            yield EntityRef(
                entity_type=EntityType.COUNTRY,
                external_id=country.external_id,
                name=country.name,
                slug=country.slug,
                popularity=index.popularity_from_rank(country.popularity_rank, total_countries),
                product_ids=product_ids,
                context={"country": country.name, "entity": country.name},
            )

    def _cities(self, index: CatalogIndex):
        total_cities = max(len(index.cities), 1)
        for city in sorted(index.cities.values(), key=lambda c: -(c.product_count or 0)):
            product_ids = index.by_city.get(city.external_id, [])
            if not product_ids:
                continue
            yield EntityRef(
                entity_type=EntityType.CITY,
                external_id=city.external_id,
                name=city.name,
                slug=city.slug,
                popularity=index.popularity_from_rank(city.popularity_rank, total_cities),
                product_ids=product_ids,
                context={
                    "city": city.name,
                    "entity": city.name,
                    "country": city.country_name or "",
                },
            )

    def _attractions(self, index: CatalogIndex):
        total_attractions = max(len(index.attractions), 1)
        for attraction in sorted(index.attractions.values(), key=lambda a: -(a.product_count or 0)):
            product_ids = index.by_attraction.get(attraction.external_id, [])
            if not product_ids:
                continue
            city = index.cities.get(attraction.city_external_id or "")
            yield EntityRef(
                entity_type=EntityType.ATTRACTION,
                external_id=attraction.external_id,
                name=attraction.name,
                slug=attraction.slug,
                popularity=index.popularity_from_rank(
                    attraction.popularity_rank, total_attractions
                ),
                product_ids=product_ids,
                context={
                    "attraction": attraction.name,
                    "entity": attraction.name,
                    "city": city.name if city else "",
                },
            )

    def _categories(self, index: CatalogIndex):
        for (category_id, city_id), product_ids in sorted(
            index.by_category_city.items(), key=lambda kv: -len(kv[1])
        ):
            category = index.categories.get(category_id)
            city = index.cities.get(city_id)
            if category is None or city is None:
                continue
            yield EntityRef(
                entity_type=EntityType.CATEGORY,
                external_id=f"{category_id}@{city_id}",
                name=f"{category.title} — {city.name}",
                slug=f"{category.slug}-{city.slug}",
                popularity=index.product_popularity(product_ids),
                product_ids=product_ids,
                context={
                    "category": category.title.lower(),
                    "city": city.name,
                    "entity": category.title,
                },
            )

    def _collections(self, index: CatalogIndex):
        for (collection_id, city_id), product_ids in sorted(
            index.by_collection_city.items(), key=lambda kv: -len(kv[1])
        ):
            collection = index.collections.get(collection_id)
            city = index.cities.get(city_id)
            if collection is None or city is None:
                continue
            yield EntityRef(
                entity_type=EntityType.COLLECTION,
                external_id=f"{collection_id}@{city_id}",
                name=f"{collection.title} — {city.name}",
                slug=f"{collection.slug}-{city.slug}",
                popularity=index.product_popularity(product_ids),
                product_ids=product_ids,
                context={
                    "theme": collection.title.lower(),
                    "city": city.name,
                    "entity": collection.title,
                },
            )

    def _products(self, index: CatalogIndex):
        for product in sorted(
            index.products,
            key=lambda p: p.popularity_rank if p.popularity_rank is not None else 9999,
        )[:150]:
            city = index.cities.get(product.city_external_id or "")
            attraction_name = (
                product.attractions[0].name if product.attractions else None
            ) or product.title
            yield EntityRef(
                entity_type=EntityType.PRODUCT,
                external_id=product.external_id,
                name=product.title,
                slug=product.slug,
                popularity=index.popularity_from_rank(product.popularity_rank, len(index.products)),
                product_ids=[product.external_id],
                context={
                    "entity": attraction_name,
                    "attraction": attraction_name,
                    "city": city.name if city else "",
                    "theme": (
                        (product.collections[0].title or "").lower() if product.collections else ""
                    ),
                },
            )

    # -------------------------------------------------------------- scoring
    def _consider(
        self,
        market: Market,
        index: CatalogIndex,
        entity: EntityRef,
        cluster: ClusterDefinition,
        stats: DiscoveryStats,
        diversity: dict[str, int],
    ) -> None:
        values = {**entity.context, "entity": entity.context.get("entity", entity.name)}
        if any(not values.get(name) for name in cluster.placeholders):
            return

        primary_query = render_pattern(cluster.primary_pattern, values, market=market)
        if not primary_query:
            return
        secondary = [
            rendered
            for pattern in cluster.secondary_patterns
            if (rendered := render_pattern(pattern, values, market=market))
        ]

        inventory_depth = len(entity.product_ids)
        if inventory_depth < cluster.min_inventory:
            stats.thin += 1
            return

        verdict = self.dedup.check_topic(
            market,
            entity_type=entity.entity_type,
            entity_external_id=entity.external_id,
            entity_name=entity.name,
            intent=cluster.intent,
            primary_query=primary_query,
        )
        key = topic_key(market, entity.entity_type, entity.external_id, cluster.intent)
        existing = self.session.scalar(
            select(TopicCandidate).where(
                TopicCandidate.market == market, TopicCandidate.topic_key == key
            )
        )
        if verdict.is_duplicate and (
            existing is None or existing.id != verdict.conflicting_topic_id
        ):
            stats.duplicates += 1
            if existing is not None and existing.status == TopicStatus.CANDIDATE:
                existing.status = TopicStatus.DUPLICATE
                existing.status_reason = verdict.reason
            return

        products = [
            index.products_by_id[pid] for pid in entity.product_ids if pid in index.products_by_id
        ]
        demand = self.demand.get_demand(
            primary_query,
            market,
            entity_popularity=entity.popularity,
            inventory_depth=inventory_depth,
            intent=cluster.intent,  # type: ignore[call-arg]
        )
        diversity_key = f"{entity.entity_type}:{cluster.intent}"
        diversity_signal = max(0.0, 1.0 - diversity.get(diversity_key, 0) / 12.0)

        result = score_topic(
            ScoreInputs(
                demand_score=demand.score,
                demand_confidence=demand.confidence,
                inventory_depth=inventory_depth,
                min_inventory=cluster.min_inventory,
                entity_popularity=entity.popularity,
                product_quality=product_quality_signal(
                    [p.rating for p in products], [p.reviews_count for p in products]
                ),
                commercial_relevance=commercial_relevance_signal(
                    has_price=any(p.price is not None for p in products),
                    available_count=sum(1 for p in products if p.available),
                    total_count=len(products) or 1,
                    intent_is_commercial=cluster.intent in COMMERCIAL_INTENTS,
                ),
                freshness=index.freshness(entity.product_ids),
                content_diversity=diversity_signal,
                cluster_weight=cluster.weight,
            )
        )

        canonical = canonicalize_query(primary_query, market)
        if existing is None:
            existing = TopicCandidate(
                market=market,
                topic_key=key,
                topic_slug=topic_slug(market, entity.name, cluster.intent),
                entity_type=entity.entity_type,
                entity_external_id=entity.external_id,
                entity_name=entity.name,
                intent=cluster.intent,
                primary_query=primary_query,
                canonical_query=canonical,
                status=TopicStatus.CANDIDATE,
            )
            self.session.add(existing)
            stats.created += 1
        else:
            if existing.status not in {
                TopicStatus.CANDIDATE,
                TopicStatus.DUPLICATE,
                TopicStatus.REJECTED,
            }:
                return
            existing.status = TopicStatus.CANDIDATE
            existing.status_reason = None
            stats.updated += 1

        existing.primary_query = primary_query
        existing.canonical_query = canonical
        existing.secondary_queries = secondary
        existing.relevant_product_ids = entity.product_ids[:40]
        existing.inventory_depth = inventory_depth
        existing.topic_score = result.score
        existing.score_breakdown = result.as_dict()
        existing.demand_confidence = result.confidence
        existing.demand_source = demand.source
        existing.requires_volatile_facts = cluster.requires_volatile_facts
        stats.by_entity_type[entity.entity_type] += 1
        diversity[diversity_key] = diversity.get(diversity_key, 0) + 1

        self._record_query_candidates(market, entity, cluster, primary_query, secondary, demand)

    def _record_query_candidates(
        self,
        market: Market,
        entity: EntityRef,
        cluster: ClusterDefinition,
        primary_query: str,
        secondary: list[str],
        demand: Any,
    ) -> None:
        for query in [primary_query, *secondary]:
            canonical = canonicalize_query(query, market)
            cache_key = (market, canonical)
            if cache_key in self._seen_queries:
                continue
            existing = self.session.scalar(
                select(QueryCandidate).where(
                    QueryCandidate.market == market, QueryCandidate.canonical_query == canonical
                )
            )
            self._seen_queries.add(cache_key)
            if existing is None:
                self.session.add(
                    QueryCandidate(
                        market=market,
                        query=query,
                        canonical_query=canonical,
                        entity_type=entity.entity_type,
                        entity_external_id=entity.external_id,
                        intent=cluster.intent,
                        demand_score=demand.score,
                        demand_source=demand.source,
                        confidence=demand.confidence,
                    )
                )

    def _diversity_baseline(self, market: Market) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        rows = self.session.scalars(
            select(TopicCandidate).where(
                TopicCandidate.market == market,
                TopicCandidate.status.in_(
                    [TopicStatus.USED, TopicStatus.QUEUED, TopicStatus.GENERATING]
                ),
            )
        ).all()
        for row in rows:
            counts[f"{row.entity_type}:{row.intent}"] += 1
        return counts


def select_topics_for_generation(
    session: Session, market: Market, limit: int
) -> list[TopicCandidate]:
    """Highest-scoring candidates that are not already in the pipeline."""
    return list(
        session.scalars(
            select(TopicCandidate)
            .where(
                TopicCandidate.market == market,
                TopicCandidate.status == TopicStatus.CANDIDATE,
            )
            .order_by((TopicCandidate.topic_score + TopicCandidate.boost).desc())
            .limit(limit)
        ).all()
    )


__all__ = [
    "COMMERCIAL_INTENTS",
    "CatalogIndex",
    "DiscoveryStats",
    "EntityRef",
    "TopicDiscoveryService",
    "select_topics_for_generation",
]
