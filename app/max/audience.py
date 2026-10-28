"""Max Russia-only audience filter (addendum v1.1 §6.1).

MAX is for people **in Russia**, not “all Russian speakers worldwide”.
Telegram RU may still take broader RU topics; Max must pass this gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.topics.geo import TopicGeo

Relevance = Literal["high", "medium", "low", "none"]
Benefit = Literal[
    "local_leisure",
    "domestic_trip",
    "outbound_trip_from_ru",
    "russia_relevant_news",
    "culture_curiosity",
]


@dataclass(slots=True)
class MaxAudienceDecision:
    channel: str = "max_ru"
    audience_country: str = "RU"
    topic_id: str | None = None
    relevance_for_russia: Relevance = "none"
    benefit: Benefit | None = None
    covered_region_ids: list[str] = field(default_factory=list)
    practicality_verified: bool = False
    requires_country_entry_verification: bool = False
    should_publish: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


#: Intents that usually mean local leisure / weekend ideas.
_LOCAL_INTENTS = frozenset(
    {
        "things_to_do",
        "weekend",
        "with_kids",
        "free",
        "rainy_day",
        "evening",
        "museum",
        "exhibition",
        "local",
    }
)

#: Intents that often imply trip planning (domestic or outbound).
_TRIP_INTENTS = frozenset(
    {
        "itinerary",
        "trip",
        "travel",
        "visit",
        "guide",
        "first_time",
        "days",
        "things_to_do",
        "museum",
        "attraction",
    }
)

#: Foreign local-news flavours with no trip value for residents of Russia.
_FOREIGN_LOCAL_ONLY = frozenset(
    {
        "expat",
        "local_only",
        "neighbourhood",
        "resident_news",
    }
)


def _intent_tokens(intent: str | None) -> set[str]:
    raw = (intent or "").casefold().replace("-", "_")
    parts = {p for p in raw.replace(" ", "_").split("_") if p}
    parts.add(raw)
    return parts


class MaxRussiaAudienceGate:
    """Decide whether a RU editorial idea may go to Max."""

    def evaluate(
        self,
        *,
        geo: TopicGeo,
        intent: str | None = None,
        topic_id: str | None = None,
        entity_name: str | None = None,
        practicality_verified: bool = False,
        entry_rules_mentioned: bool = False,
        expired_local_event: bool = False,
        product_available_on_ru_store: bool | None = None,
        audience_axis: str | None = None,
        editorial_mechanic: str | None = None,
        recommends_travel: bool = False,
    ) -> MaxAudienceDecision:
        if expired_local_event:
            return MaxAudienceDecision(
                topic_id=topic_id,
                relevance_for_russia="none",
                should_publish=False,
                reason="local event already ended before publish",
            )

        tokens = _intent_tokens(intent)
        city = geo.city_id
        regions = [city] if city else []

        if geo.is_russia:
            if tokens & _LOCAL_INTENTS or not (tokens & _TRIP_INTENTS):
                benefit: Benefit = "local_leisure"
            else:
                benefit = "domestic_trip"
            return MaxAudienceDecision(
                topic_id=topic_id,
                relevance_for_russia="high",
                benefit=benefit,
                covered_region_ids=regions,
                practicality_verified=practicality_verified or True,
                requires_country_entry_verification=False,
                should_publish=True,
                reason="domestic Russia topic for local leisure or trip",
            )

        from app.editorial.mechanics import CULTURE_AXES, CULTURE_MECHANICS

        culture = audience_axis in CULTURE_AXES or editorial_mechanic in CULTURE_MECHANICS

        # Foreign destination: only as outbound travel *from* Russia — unless it is
        # a genuine culture/curiosity story without bogus logistics.
        if tokens & _FOREIGN_LOCAL_ONLY and not culture:
            return MaxAudienceDecision(
                topic_id=topic_id,
                relevance_for_russia="none",
                should_publish=False,
                reason="foreign local/expat topic without value for residents of Russia",
            )

        if culture and not recommends_travel:
            return MaxAudienceDecision(
                topic_id=topic_id,
                relevance_for_russia="medium",
                benefit="culture_curiosity",
                covered_region_ids=[],
                practicality_verified=True,
                requires_country_entry_verification=False,
                should_publish=True,
                reason="international culture/curiosity without practical travel advice",
            )

        if product_available_on_ru_store is False:
            return MaxAudienceDecision(
                topic_id=topic_id,
                relevance_for_russia="none",
                benefit="outbound_trip_from_ru",
                covered_region_ids=[],
                practicality_verified=False,
                requires_country_entry_verification=entry_rules_mentioned,
                should_publish=False,
                reason="foreign destination without RU-store product / practical access",
            )

        # WeGoTrip RU catalogue foreign items = outbound ideas for people in Russia.
        # Entry/visa claims still need verification when mentioned in copy.
        return MaxAudienceDecision(
            topic_id=topic_id,
            relevance_for_russia="medium",
            benefit="outbound_trip_from_ru",
            covered_region_ids=[],
            practicality_verified=practicality_verified,
            requires_country_entry_verification=entry_rules_mentioned,
            should_publish=True,
            reason=(
                "outbound trip idea from Russia"
                f"{' (entry rules need verification)' if entry_rules_mentioned else ''}"
                f"{f'; entity={entity_name}' if entity_name else ''}"
            ),
        )


__all__ = [
    "Benefit",
    "MaxAudienceDecision",
    "MaxRussiaAudienceGate",
    "Relevance",
]
