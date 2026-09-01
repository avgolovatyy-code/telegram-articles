"""Search demand signals.

There is no keyword/SEO provider wired in, so demand is *heuristic* and every
candidate is labelled ``demand_source="heuristic"`` with a deliberately low
confidence. A real provider (DataForSEO, internal WeGoTrip SEO data, …) can be
plugged in behind :class:`SearchDemandProvider` without touching topic discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol, runtime_checkable

from app.config import Market, Settings, get_settings

#: Confidence ceiling for heuristic estimates — never claim a query is "popular".
HEURISTIC_MAX_CONFIDENCE = 0.55


@dataclass(frozen=True, slots=True)
class DemandSignal:
    query: str
    market: Market
    score: float | None
    source: str
    confidence: float
    volume: int | None = None
    trend: float | None = None


@runtime_checkable
class SearchDemandProvider(Protocol):
    name: str

    def get_demand(
        self,
        query: str,
        market: Market,
        *,
        entity_popularity: float = 0.0,
        inventory_depth: int = 0,
    ) -> DemandSignal: ...


class HeuristicDemandProvider:
    """Estimates relative demand from intent shape, catalogue depth and popularity.

    The returned ``score`` is a *relative* ranking signal, not a search volume.
    """

    name = "heuristic"

    #: Broad head-intents attract more search traffic than long-tail modifiers.
    #: Planning / cultural-programme intents rank above product-shaped queries so the
    #: queue prefers "what to see / how to spend a day" over audio-guide shopping topics.
    _INTENT_PRIOR: ClassVar[dict[str, float]] = {
        "things_to_do": 1.0,
        "attractions": 0.95,
        "what_to_see": 0.95,
        "one_day": 0.9,
        "itinerary": 0.9,
        "museums": 0.85,
        "guide": 0.85,
        "travel_guide": 0.85,
        "two_days": 0.8,
        "three_days": 0.8,
        "best_in_city": 0.8,
        "first_time": 0.75,
        "first_time_in_city": 0.7,
        "best_cities": 0.65,
        "walking_route": 0.65,
        "independent_trip": 0.6,
        "with_kids": 0.55,
        "with_kids_in_city": 0.5,
        "tickets": 0.55,
        "walking_tour": 0.5,
        "self_guided_tour": 0.45,
        "self_guided_in_city": 0.45,
        "self_guided_routes": 0.4,
        "audio_guide": 0.4,
        "ticket_with_audio": 0.4,
        "themed_walking_tour": 0.35,
        "themed_experience": 0.4,
        "how_long": 0.45,
        "best_time": 0.45,
        "nearby": 0.4,
        "rainy_day": 0.4,
        "at_night": 0.4,
    }

    def get_demand(
        self,
        query: str,
        market: Market,
        *,
        entity_popularity: float = 0.0,
        inventory_depth: int = 0,
        intent: str | None = None,
    ) -> DemandSignal:
        prior = self._INTENT_PRIOR.get(intent or "", 0.5)
        depth_signal = min(1.0, inventory_depth / 20.0)
        raw = 0.55 * prior + 0.25 * entity_popularity + 0.20 * depth_signal
        # Very long queries are long-tail: lower absolute demand, still valid topics.
        length_penalty = min(0.15, max(0, len(query.split()) - 6) * 0.03)
        score = max(0.0, min(1.0, raw - length_penalty))
        confidence = min(HEURISTIC_MAX_CONFIDENCE, 0.25 + 0.3 * prior)
        return DemandSignal(
            query=query,
            market=market,
            score=score,
            source=self.name,
            confidence=confidence,
        )


class NullDemandProvider:
    """Reports no demand signal at all; scoring redistributes the weight."""

    name = "none"

    def get_demand(
        self,
        query: str,
        market: Market,
        *,
        entity_popularity: float = 0.0,
        inventory_depth: int = 0,
        intent: str | None = None,
    ) -> DemandSignal:
        return DemandSignal(
            query=query, market=market, score=None, source=self.name, confidence=0.0
        )


def build_demand_provider(settings: Settings | None = None) -> SearchDemandProvider:
    settings = settings or get_settings()
    if settings.search_demand_provider == "none":
        return NullDemandProvider()
    return HeuristicDemandProvider()


__all__ = [
    "HEURISTIC_MAX_CONFIDENCE",
    "DemandSignal",
    "HeuristicDemandProvider",
    "NullDemandProvider",
    "SearchDemandProvider",
    "build_demand_provider",
]
