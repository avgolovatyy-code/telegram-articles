"""Product matching and ranking.

Products are chosen by code *before* the writer prompt is built; the model only ever
sees the products it is allowed to mention. Ranking is relevance-first — an expensive
but irrelevant tour never wins (spec §25).

Recommended weights::

    45% semantic relevance
    20% popularity
    15% rating / review quality
    10% availability
    10% diversity / commercial fit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.db.models import Product, TopicCandidate
from app.topics.dedup import cosine_similarity, vectorize

RANK_WEIGHTS: dict[str, float] = {
    "relevance": 0.45,
    "popularity": 0.20,
    "quality": 0.15,
    "availability": 0.10,
    "commercial_fit": 0.10,
}

#: A candidate below this relevance is dropped rather than padded into the article.
MIN_RELEVANCE = 0.12

MAX_PRODUCTS_PER_ARTICLE = 2


@dataclass(slots=True)
class RankedProduct:
    product: Product
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    placement: str = "compact"


def _product_text(product: Product) -> str:
    parts = [
        product.title,
        product.short_description or "",
        " ".join(product.highlights or []),
        product.primary_category or "",
        " ".join(link.title or "" for link in product.categories),
        " ".join(link.title or "" for link in product.collections),
        " ".join(link.name or "" for link in product.attractions),
    ]
    return " ".join(part for part in parts if part)


def relevance(topic_text: str, product: Product) -> float:
    return cosine_similarity(vectorize(topic_text), vectorize(_product_text(product)))


def _popularity(product: Product, max_rank: int) -> float:
    if product.popularity_rank is None:
        return 0.35
    return max(0.0, 1.0 - product.popularity_rank / max(max_rank, 1))


def _quality(product: Product) -> float:
    if product.rating is None:
        return 0.35
    rating_part = min(1.0, product.rating / 5.0)
    reviews = product.reviews_count or 0
    confidence = min(1.0, reviews / 50.0)
    return round(rating_part * (0.6 + 0.4 * confidence), 4)


def _availability(product: Product) -> float:
    if not product.available or not product.published:
        return 0.0
    return 1.0 if product.price is not None else 0.7


def _commercial_fit(product: Product, *, entity_match: bool) -> float:
    # Do not boost audioguides just for being audioguides — relevance + entity match
    # already decide whether a tour belongs in a cultural plan.
    score = 0.45 if product.price is not None else 0.25
    if entity_match:
        score += 0.35
    return min(1.0, score)


class ProductSelector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def rank(
        self,
        topic: TopicCandidate,
        candidates: list[Product],
        *,
        limit: int = MAX_PRODUCTS_PER_ARTICLE,
    ) -> list[RankedProduct]:
        available = [p for p in candidates if p.available and p.published]
        if not available:
            return []

        topic_text = " ".join(
            [topic.primary_query, topic.entity_name, *(topic.secondary_queries or [])]
        )
        max_rank = max((p.popularity_rank or 0 for p in available), default=1) or 1

        ranked: list[RankedProduct] = []
        for product in available:
            entity_match = _matches_entity(product, topic)
            components = {
                "relevance": relevance(topic_text, product),
                "popularity": _popularity(product, max_rank),
                "quality": _quality(product),
                "availability": _availability(product),
                "commercial_fit": _commercial_fit(product, entity_match=entity_match),
            }
            # An exact entity match is strong evidence the product belongs here even
            # when the wording differs from the query.
            if entity_match:
                components["relevance"] = min(1.0, components["relevance"] + 0.25)
            score = sum(components[key] * RANK_WEIGHTS[key] for key in components)
            if components["relevance"] < MIN_RELEVANCE and not entity_match:
                continue
            ranked.append(
                RankedProduct(
                    product=product,
                    score=round(score, 4),
                    breakdown={k: round(v, 4) for k, v in components.items()},
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        selected = _diversify(ranked, limit)
        # Prefer quiet compact cards; hero shop-window layouts push a sales tone.
        for item in selected:
            item.placement = "compact"
        return selected

    def select(
        self,
        topic: TopicCandidate,
        catalog_products: dict[str, Product],
        *,
        limit: int = MAX_PRODUCTS_PER_ARTICLE,
    ) -> list[RankedProduct]:
        candidates = [
            catalog_products[pid]
            for pid in (topic.relevant_product_ids or [])
            if pid in catalog_products
        ]
        return self.rank(topic, candidates, limit=limit)


def _matches_entity(product: Product, topic: TopicCandidate) -> bool:
    entity_id = topic.entity_external_id.split("@", 1)[0]
    match topic.entity_type:
        case "city":
            return product.city_external_id == entity_id
        case "country":
            return product.country_external_id == entity_id
        case "attraction":
            return any(link.attraction_external_id == entity_id for link in product.attractions)
        case "category":
            return any(link.category_external_id == entity_id for link in product.categories)
        case "collection":
            return any(link.collection_external_id == entity_id for link in product.collections)
        case "product":
            return product.external_id == entity_id
    return False


def _diversify(ranked: list[RankedProduct], limit: int) -> list[RankedProduct]:
    """Avoid three near-identical tours of the same attraction in one article."""
    chosen: list[RankedProduct] = []
    used_attractions: set[str] = set()
    for item in ranked:
        if len(chosen) >= limit:
            break
        attraction_ids = {link.attraction_external_id for link in item.product.attractions}
        if attraction_ids and attraction_ids & used_attractions and len(chosen) >= 2:
            continue
        chosen.append(item)
        used_attractions |= attraction_ids
    if len(chosen) < min(limit, len(ranked)):
        for item in ranked:
            if len(chosen) >= limit:
                break
            if item not in chosen:
                chosen.append(item)
    return chosen


def product_facts(product: Product) -> list[str]:
    """Trusted API facts a writer may state verbatim (spec §16.1)."""
    facts: list[str] = []
    if product.duration_min and product.duration_max:
        if product.duration_min == product.duration_max:
            facts.append(f"{product.title}: duration {product.duration_min} min (WeGoTrip API)")
        else:
            facts.append(
                f"{product.title}: duration {product.duration_min}-{product.duration_max} min "
                "(WeGoTrip API)"
            )
    if product.price is not None and product.currency_code:
        facts.append(
            f"{product.title}: from {product.price} {product.currency_code} (WeGoTrip API)"
        )
    if product.rating is not None:
        facts.append(
            f"{product.title}: rating {product.rating}"
            + (f" from {product.reviews_count} reviews" if product.reviews_count else "")
            + " (WeGoTrip API)"
        )
    if product.distance:
        facts.append(f"{product.title}: route length {product.distance} (WeGoTrip API)")
    for inclusion in (product.inclusions or [])[:4]:
        facts.append(f"{product.title} includes: {inclusion} (WeGoTrip API)")
    for exclusion in (product.exclusions or [])[:3]:
        facts.append(f"{product.title} does not include: {exclusion} (WeGoTrip API)")
    if product.start_location:
        facts.append(f"{product.title}: starts at {product.start_location} (WeGoTrip API)")
    return facts


def product_summary(product: Product) -> dict[str, Any]:
    """Compact product payload for the writer — never the full API JSON (spec §48.2)."""
    return {
        "id": product.external_id,
        "title": product.title,
        "short_description": (product.short_description or product.description or "")[:600] or None,
        "highlights": (product.highlights or [])[:5],
        "duration_min": product.duration_min,
        "duration_max": product.duration_max,
        "price": product.price,
        "currency": product.currency_code,
        "rating": product.rating,
        "reviews_count": product.reviews_count,
        "categories": [link.title for link in product.categories if link.title][:4],
        "collections": [link.title for link in product.collections if link.title][:4],
        "attractions": [link.name for link in product.attractions if link.name][:4],
        "audioguide": bool((product.types or {}).get("audioguide")),
        "available": product.available,
    }


__all__ = [
    "MAX_PRODUCTS_PER_ARTICLE",
    "MIN_RELEVANCE",
    "RANK_WEIGHTS",
    "ProductSelector",
    "RankedProduct",
    "product_facts",
    "product_summary",
    "relevance",
]
