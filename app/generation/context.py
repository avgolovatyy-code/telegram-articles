"""Writer context builder.

The writer never receives "write an article about Paris". It receives a structured
context: the entity, the queries, trusted catalogue facts, externally verified facts,
the pre-selected products, the media it is allowed to place and the style constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings, get_settings
from app.db.models import Attraction, City, Country, Product, TopicCandidate
from app.generation.product_selection import RankedProduct, product_facts, product_summary
from app.media_assets import MediaCandidate

#: Cover preference (spec §23/§27): attraction → city → product.
COVER_PRIORITY = ("attraction", "city", "product")

FORBIDDEN_CLAIM_TOPICS_EN = [
    "opening hours or closing days that are not in verified_facts",
    "ticket prices of the venue itself that are not in verified_facts",
    "current exhibitions, renovations or temporary restrictions",
    "transport disruptions or timetable details",
    "skip-the-line access that is not stated in the product data",
    "any invented review, quotation, rating or discount",
]

FORBIDDEN_CLAIM_TOPICS_RU = [
    "часы работы и выходные дни, которых нет в verified_facts",
    "цены самого объекта, которых нет в verified_facts",
    "текущие выставки, ремонты и временные ограничения",
    "изменения транспорта и расписания",
    "вход без очереди, если этого нет в данных товара",
    "любые выдуманные отзывы, цитаты, рейтинги и скидки",
]


@dataclass(slots=True)
class WriterContext:
    market: Market
    topic: TopicCandidate
    products: list[RankedProduct]
    media: list[MediaCandidate]
    catalog_facts: list[str]
    verified_facts: list[dict[str, Any]] = field(default_factory=list)
    entity: dict[str, Any] = field(default_factory=dict)
    audio: list[dict[str, Any]] = field(default_factory=list)
    catalog_attractions: list[dict[str, Any]] = field(default_factory=list)

    def as_payload(self, settings: Settings) -> dict[str, Any]:
        forbidden = FORBIDDEN_CLAIM_TOPICS_RU if self.market == "ru" else FORBIDDEN_CLAIM_TOPICS_EN
        placement_cap = min(3, len(self.products))
        return {
            "market": self.market,
            "primary_query": self.topic.primary_query,
            "secondary_queries": list(self.topic.secondary_queries or []),
            "intent": self.topic.intent,
            "entity": self.entity,
            "catalog_context": {
                "entity_type": self.topic.entity_type,
                "inventory_depth": self.topic.inventory_depth,
            },
            "catalog_attractions": self.catalog_attractions,
            "catalog_facts": self.catalog_facts,
            "verified_facts": self.verified_facts,
            # Full ranked set for naming places / durations / ratings; cards are capped.
            "products": [product_summary(item.product) for item in self.products],
            "allowed_media": [item.as_context() for item in self.media],
            "allowed_audio": self.audio,
            "brand_style": {
                "voice": "friendly, plain, specific, lightly humorous",
                "purpose": (
                    "help someone preparing for or already on a trip with concrete "
                    "places, order and trade-offs drawn from the WeGoTrip catalogue"
                ),
                "references": ["Aviasales", "T—J"],
                "avoid": [
                    "ad pathos",
                    "AI boilerplate",
                    "keyword stuffing",
                    "catalogue / shop-window tone",
                    "watery philosophy without named places",
                    "recommending an audio guide for every stop",
                    "naming competitor apps or ticket resellers",
                ],
                "humour_must_not": [
                    "mock people, nationalities, cities or the reader",
                    "use stereotypes or sensitive traits",
                ],
            },
            "forbidden_claims": forbidden,
            "article_constraints": {
                "min_chars": settings.article_target_min_chars,
                "max_chars": settings.article_target_max_chars,
                "hard_max_chars": settings.article_max_chars,
                "preferred_products": 1,
                "max_products": placement_cap,
                "min_named_catalog_attractions": min(4, max(2, len(self.catalog_attractions))),
                "products_are_optional": True,
                "recommend_wegotrip_only": True,
                "max_hashtags": settings.max_hashtags if settings.enable_hashtags else 0,
                "sections_min": 3,
                "sections_max": 8,
            },
        }


class ContextBuilder:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def build(
        self,
        topic: TopicCandidate,
        products: list[RankedProduct],
        *,
        verified_facts: list[dict[str, Any]] | None = None,
    ) -> WriterContext:
        market: Market = topic.market  # type: ignore[assignment]
        entity = self._entity_payload(topic, market)
        media = self._collect_media(topic, products, market)
        attractions = self._catalog_attractions(topic, market, products)
        facts: list[str] = []
        for item in products:
            facts.extend(product_facts(item.product))
            for link in item.product.attractions:
                if link.name:
                    facts.append(
                        f"{item.product.title} covers / is linked to {link.name} (WeGoTrip API)"
                    )
        facts.extend(self._entity_facts(topic, entity))
        facts.extend(self._attraction_facts(attractions))

        audio = [
            {
                "product_id": item.product.external_id,
                "url": item.product.audio_preview_url,
                "title": item.product.title,
            }
            for item in products
            if item.product.audio_preview_url
        ]

        return WriterContext(
            market=market,
            topic=topic,
            products=products,
            media=media,
            catalog_facts=_dedupe_facts(facts)[:80],
            verified_facts=verified_facts or [],
            entity=entity,
            audio=audio,
            catalog_attractions=attractions,
        )

    # -------------------------------------------------------------- entities
    def _entity_payload(self, topic: TopicCandidate, market: Market) -> dict[str, Any]:
        entity_id = topic.entity_external_id.split("@", 1)[0]
        payload: dict[str, Any] = {
            "type": topic.entity_type,
            "id": topic.entity_external_id,
            "name": topic.entity_name,
        }
        match topic.entity_type:
            case "city":
                city_row = self._city(market, entity_id)
                if city_row:
                    payload |= {"country": city_row.country_name, "slug": city_row.slug}
            case "country":
                country_row = self._country(market, entity_id)
                if country_row:
                    payload |= {"slug": country_row.slug, "cities": country_row.city_count}
            case "attraction":
                attraction_row = self._attraction(market, entity_id)
                if attraction_row:
                    city = self._city(market, attraction_row.city_external_id or "")
                    payload |= {
                        "slug": attraction_row.slug,
                        "city": city.name if city else None,
                    }
            case "category" | "collection":
                _, _, city_id = topic.entity_external_id.partition("@")
                city = self._city(market, city_id)
                payload |= {"city": city.name if city else None}
            case "product":
                product = self._product(market, entity_id)
                if product:
                    city = self._city(market, product.city_external_id or "")
                    payload |= {"city": city.name if city else None, "slug": product.slug}
        return payload

    def _entity_facts(self, topic: TopicCandidate, entity: dict[str, Any]) -> list[str]:
        facts = [
            f"WeGoTrip currently has {topic.inventory_depth} available products matching "
            f"{topic.entity_name} (WeGoTrip API)."
        ]
        if entity.get("country"):
            facts.append(f"{topic.entity_name} is in {entity['country']} (WeGoTrip API).")
        if entity.get("city"):
            facts.append(f"{topic.entity_name} is in {entity['city']} (WeGoTrip API).")
        return facts

    def _catalog_attractions(
        self, topic: TopicCandidate, market: Market, products: list[RankedProduct]
    ) -> list[dict[str, Any]]:
        """Concrete places from the WeGoTrip catalogue the writer must lean on."""
        city_id = self._resolve_city_id(topic, products)
        rows: list[Attraction] = []
        if city_id:
            rows = list(
                self.session.scalars(
                    select(Attraction)
                    .where(Attraction.market == market, Attraction.city_external_id == city_id)
                    .order_by(Attraction.popularity_rank.asc().nulls_last(), Attraction.name.asc())
                    .limit(15)
                ).all()
            )
        # Always include attractions linked to the selected products.
        seen = {row.external_id for row in rows}
        for item in products:
            for link in item.product.attractions:
                if not link.attraction_external_id or link.attraction_external_id in seen:
                    continue
                attraction = self._attraction(market, link.attraction_external_id)
                if attraction is None:
                    continue
                rows.append(attraction)
                seen.add(attraction.external_id)

        return [
            {
                "id": row.external_id,
                "name": row.name,
                "slug": row.slug,
                "product_count": row.product_count,
                "popularity_rank": row.popularity_rank,
            }
            for row in rows[:18]
        ]

    def _attraction_facts(self, attractions: list[dict[str, Any]]) -> list[str]:
        facts: list[str] = []
        for row in attractions[:12]:
            name = row.get("name")
            if not name:
                continue
            count = row.get("product_count") or 0
            if count:
                facts.append(
                    f"{name}: {count} linked WeGoTrip product(s) in the catalogue (WeGoTrip API)"
                )
            else:
                facts.append(f"{name} is listed as a WeGoTrip catalogue attraction (WeGoTrip API)")
        return facts

    def _resolve_city_id(
        self, topic: TopicCandidate, products: list[RankedProduct]
    ) -> str | None:
        entity_id = topic.entity_external_id.split("@", 1)[0]
        if topic.entity_type == "city":
            return entity_id
        if topic.entity_type in {"category", "collection"}:
            _, _, city_id = topic.entity_external_id.partition("@")
            return city_id or None
        if topic.entity_type == "attraction":
            attraction = self._attraction(topic.market, entity_id)  # type: ignore[arg-type]
            return attraction.city_external_id if attraction else None
        if products:
            return products[0].product.city_external_id
        return None

    # ----------------------------------------------------------------- media
    def _collect_media(
        self, topic: TopicCandidate, products: list[RankedProduct], market: Market
    ) -> list[MediaCandidate]:
        """Only media returned by the WeGoTrip API is ever offered to the writer."""
        candidates: list[MediaCandidate] = []
        seen: set[str] = set()

        def add(
            url: str | None,
            *,
            kind: str,
            entity_type: str,
            entity_id: str | None,
            product_id: str | None = None,
            caption: str | None = None,
        ) -> None:
            if not url or not url.startswith("http") or url in seen:
                return
            seen.add(url)
            candidates.append(
                MediaCandidate(
                    id=f"m{len(candidates) + 1}",
                    url=url,
                    kind=kind,
                    source_entity_type=entity_type,
                    source_entity_id=entity_id,
                    product_external_id=product_id,
                    caption=caption,
                )
            )

        entity_id = topic.entity_external_id.split("@", 1)[0]
        if topic.entity_type == "attraction":
            attraction = self._attraction(market, entity_id)
            if attraction:
                add(
                    attraction.preview,
                    kind="photo",
                    entity_type="attraction",
                    entity_id=attraction.external_id,
                    caption=attraction.name,
                )
        city_id = entity_id if topic.entity_type == "city" else None
        if city_id is None and topic.entity_type in {"category", "collection"}:
            _, _, city_id = topic.entity_external_id.partition("@")
        if city_id is None and products:
            city_id = products[0].product.city_external_id
        city = self._city(market, city_id or "")
        if city:
            for asset in city.media or []:
                add(
                    asset.get("url"),
                    kind="photo",
                    entity_type="city",
                    entity_id=city.external_id,
                    caption=city.name,
                )

        for item in products:
            product = item.product
            add(
                product.cover,
                kind="photo",
                entity_type="product",
                entity_id=product.external_id,
                product_id=product.external_id,
                caption=product.title,
            )
            for image in (product.images or [])[:3]:
                add(
                    image.get("url"),
                    kind="photo",
                    entity_type="product",
                    entity_id=product.external_id,
                    product_id=product.external_id,
                )

        if candidates:
            candidates[0].role = "cover"
            cover_index = _preferred_cover_index(candidates)
            if cover_index:
                candidates[0].role = "inline"
                candidates[cover_index].role = "cover"
        return candidates[:12]

    # -------------------------------------------------------------- lookups
    def _city(self, market: Market, external_id: str) -> City | None:
        if not external_id:
            return None
        return self.session.scalar(
            select(City).where(City.market == market, City.external_id == external_id)
        )

    def _country(self, market: Market, external_id: str) -> Country | None:
        return self.session.scalar(
            select(Country).where(Country.market == market, Country.external_id == external_id)
        )

    def _attraction(self, market: Market, external_id: str) -> Attraction | None:
        if not external_id:
            return None
        return self.session.scalar(
            select(Attraction).where(
                Attraction.market == market, Attraction.external_id == external_id
            )
        )

    def _product(self, market: Market, external_id: str) -> Product | None:
        return self.session.scalar(
            select(Product).where(Product.market == market, Product.external_id == external_id)
        )


def _preferred_cover_index(candidates: list[MediaCandidate]) -> int | None:
    for wanted in COVER_PRIORITY:
        for index, candidate in enumerate(candidates):
            if candidate.source_entity_type == wanted:
                return index
    return None


def _dedupe_facts(facts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for fact in facts:
        key = fact.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(fact)
    return out


__all__ = [
    "COVER_PRIORITY",
    "FORBIDDEN_CLAIM_TOPICS_EN",
    "FORBIDDEN_CLAIM_TOPICS_RU",
    "ContextBuilder",
    "MediaCandidate",
    "WriterContext",
]
