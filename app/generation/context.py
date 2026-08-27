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

    def as_payload(self, settings: Settings) -> dict[str, Any]:
        forbidden = FORBIDDEN_CLAIM_TOPICS_RU if self.market == "ru" else FORBIDDEN_CLAIM_TOPICS_EN
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
            "catalog_facts": self.catalog_facts,
            "verified_facts": self.verified_facts,
            "products": [product_summary(item.product) for item in self.products],
            "allowed_media": [item.as_context() for item in self.media],
            "allowed_audio": self.audio,
            "brand_style": {
                "voice": "friendly, plain, specific, lightly humorous",
                "references": ["Aviasales", "T—J"],
                "avoid": ["ad pathos", "AI boilerplate", "keyword stuffing"],
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
                "max_products": len(self.products),
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
        facts: list[str] = []
        for item in products:
            facts.extend(product_facts(item.product))
        facts.extend(self._entity_facts(topic, entity))

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
            catalog_facts=facts[:60],
            verified_facts=verified_facts or [],
            entity=entity,
            audio=audio,
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
                row = self._city(market, entity_id)
                if row:
                    payload |= {"country": row.country_name, "slug": row.slug}
            case "country":
                row = self._country(market, entity_id)
                if row:
                    payload |= {"slug": row.slug, "cities": row.city_count}
            case "attraction":
                row = self._attraction(market, entity_id)
                if row:
                    city = self._city(market, row.city_external_id or "")
                    payload |= {"slug": row.slug, "city": city.name if city else None}
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


__all__ = [
    "COVER_PRIORITY",
    "FORBIDDEN_CLAIM_TOPICS_EN",
    "FORBIDDEN_CLAIM_TOPICS_RU",
    "ContextBuilder",
    "MediaCandidate",
    "WriterContext",
]
