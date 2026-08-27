"""Topic scoring (spec §10).

Default weights::

    30% search demand / intent confidence
    25% inventory depth
    15% entity popularity
    10% product quality
    10% commercial relevance
     5% freshness
     5% content diversity
    - duplication penalty
    - thin-content penalty

Every weight is configurable through the ``topic_score_weights`` system setting. When
no search-demand provider is available its share is redistributed proportionally over
inventory depth and entity popularity, and the resulting confidence stays low.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DEFAULT_WEIGHTS: dict[str, float] = {
    "search_demand": 0.30,
    "inventory_depth": 0.25,
    "entity_popularity": 0.15,
    "product_quality": 0.10,
    "commercial_relevance": 0.10,
    "freshness": 0.05,
    "content_diversity": 0.05,
}

#: Where the search-demand share goes when no demand signal exists.
_DEMAND_FALLBACK_SPLIT = {"inventory_depth": 0.6, "entity_popularity": 0.4}

THIN_CONTENT_PENALTY = 0.35
DUPLICATION_PENALTY = 0.45


@dataclass(slots=True)
class ScoreInputs:
    demand_score: float | None
    demand_confidence: float
    inventory_depth: int
    min_inventory: int
    entity_popularity: float
    product_quality: float
    commercial_relevance: float
    freshness: float
    content_diversity: float
    duplication_similarity: float = 0.0
    cluster_weight: float = 1.0
    boost: float = 0.0


@dataclass(slots=True)
class ScoreResult:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def effective_weights(
    base: dict[str, float] | None, *, has_demand_signal: bool
) -> dict[str, float]:
    weights = dict(base or DEFAULT_WEIGHTS)
    if has_demand_signal:
        return weights
    demand_share = weights.pop("search_demand", 0.0)
    for key, portion in _DEMAND_FALLBACK_SPLIT.items():
        weights[key] = weights.get(key, 0.0) + demand_share * portion
    weights["search_demand"] = 0.0
    return weights


def _depth_signal(inventory_depth: int, min_inventory: int) -> float:
    if inventory_depth <= 0:
        return 0.0
    # Saturating curve: 1 product is thin, ~20 is a deep catalogue for one topic.
    target = max(min_inventory * 3, 12)
    return min(1.0, inventory_depth / target)


def score_topic(inputs: ScoreInputs, weights: dict[str, float] | None = None) -> ScoreResult:
    has_demand = inputs.demand_score is not None
    active = effective_weights(weights, has_demand_signal=has_demand)

    components = {
        "search_demand": (inputs.demand_score or 0.0) * max(inputs.demand_confidence, 0.2)
        if has_demand
        else 0.0,
        "inventory_depth": _depth_signal(inputs.inventory_depth, inputs.min_inventory),
        "entity_popularity": _clamp(inputs.entity_popularity),
        "product_quality": _clamp(inputs.product_quality),
        "commercial_relevance": _clamp(inputs.commercial_relevance),
        "freshness": _clamp(inputs.freshness),
        "content_diversity": _clamp(inputs.content_diversity),
    }

    raw = sum(components[key] * active.get(key, 0.0) for key in components)
    raw *= _clamp(inputs.cluster_weight, upper=1.5)

    penalties: dict[str, float] = {}
    if inputs.inventory_depth < inputs.min_inventory:
        penalties["thin_content"] = THIN_CONTENT_PENALTY
    if inputs.duplication_similarity > 0:
        penalties["duplication"] = DUPLICATION_PENALTY * inputs.duplication_similarity

    score = raw - sum(penalties.values()) + inputs.boost
    confidence = inputs.demand_confidence if has_demand else 0.2

    return ScoreResult(
        score=round(max(0.0, min(1.5, score)), 4),
        components={k: round(v, 4) for k, v in components.items()},
        weights={k: round(v, 4) for k, v in active.items()},
        penalties={k: round(v, 4) for k, v in penalties.items()},
        confidence=round(confidence, 4),
    )


def _clamp(value: float, *, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def product_quality_signal(ratings: list[float | None], review_counts: list[int | None]) -> float:
    """Blend of average rating and how well-reviewed the matched products are."""
    rated = [r for r in ratings if r is not None]
    counts = [c for c in review_counts if c]
    rating_part = (sum(rated) / len(rated) / 5.0) if rated else 0.4
    volume_part = min(1.0, (sum(counts) / len(counts)) / 100.0) if counts else 0.2
    return _clamp(0.7 * rating_part + 0.3 * volume_part)


def commercial_relevance_signal(
    *, has_price: bool, available_count: int, total_count: int, intent_is_commercial: bool
) -> float:
    if total_count == 0:
        return 0.0
    availability = available_count / total_count
    base = 0.5 * availability + (0.25 if has_price else 0.0)
    if intent_is_commercial:
        base += 0.25
    return _clamp(base)


__all__ = [
    "DEFAULT_WEIGHTS",
    "DUPLICATION_PENALTY",
    "THIN_CONTENT_PENALTY",
    "ScoreInputs",
    "ScoreResult",
    "commercial_relevance_signal",
    "effective_weights",
    "product_quality_signal",
    "score_topic",
]
