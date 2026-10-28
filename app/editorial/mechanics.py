"""Editorial mechanisms from competitor research (spec 3.0 §2)."""

from __future__ import annotations

from typing import Literal

EditorialMechanic = Literal[
    "weekend_utility",
    "surprising_place",
    "curious_travel_news",
    "short_fact_plus_use",
    "practical_from_russia",
    "culture_and_people",
    "playful_interaction",
    "editorial_feature",
]

EDITORIAL_MECHANICS: tuple[str, ...] = (
    "weekend_utility",
    "surprising_place",
    "curious_travel_news",
    "short_fact_plus_use",
    "practical_from_russia",
    "culture_and_people",
    "playful_interaction",
    "editorial_feature",
)

MECHANIC_SOURCES: dict[str, str] = {
    "weekend_utility": "Горбилет",
    "surprising_place": "Tripster",
    "curious_travel_news": "Авиасейлс",
    "short_fact_plus_use": "Sputnik8",
    "practical_from_russia": "Яндекс Путешествия",
    "culture_and_people": "Туту",
    "playful_interaction": "Tripster/Яндекс Путешествия",
    "editorial_feature": "WeGoTrip original",
}

AudienceAxis = Literal[
    "ru_local_leisure",
    "ru_domestic_trip",
    "ru_outbound_trip",
    "culture_and_curiosity",
    "en_local",
    "en_trip",
    "en_culture",
]

AUDIENCE_AXES: tuple[str, ...] = (
    "ru_local_leisure",
    "ru_domestic_trip",
    "ru_outbound_trip",
    "culture_and_curiosity",
    "en_local",
    "en_trip",
    "en_culture",
)

ChannelId = Literal["telegram_ru", "telegram_en", "max_ru"]

CHANNEL_IDS: tuple[str, ...] = ("telegram_ru", "telegram_en", "max_ru")

CULTURE_AXES = frozenset({"culture_and_curiosity", "en_culture"})
CULTURE_MECHANICS = frozenset(
    {
        "curious_travel_news",
        "culture_and_people",
        "playful_interaction",
        "surprising_place",
        "editorial_feature",
    }
)
PRACTICAL_TRAVEL_AXES = frozenset({"ru_outbound_trip", "ru_domestic_trip", "en_trip"})
INSTRUCTION_MECHANICS = frozenset({"practical_from_russia"})
LIGHT_MECHANICS = frozenset({"curious_travel_news", "playful_interaction", "short_fact_plus_use"})
STORY_MECHANICS = frozenset({"surprising_place", "culture_and_people", "editorial_feature"})


def default_mechanic_for_pillar(pillar: str) -> str:
    mapping = {
        "weekend_ideas": "weekend_utility",
        "weekend_plans": "weekend_utility",
        "exhibitions_museums": "short_fact_plus_use",
        "travel_news": "curious_travel_news",
        "travel_updates": "curious_travel_news",
        "city_day_route": "weekend_utility",
        "short_routes": "weekend_utility",
        "hidden_gem": "surprising_place",
        "hidden_gems": "surprising_place",
        "place_story": "culture_and_people",
        "place_stories": "culture_and_people",
        "museum_without_boredom": "short_fact_plus_use",
        "scenario_picks": "weekend_utility",
        "occasion_specific": "weekend_utility",
        "trip_planning": "practical_from_russia",
        "fresh_angle": "surprising_place",
        "community_poll": "playful_interaction",
        "engagement": "playful_interaction",
        "product_in_context": "short_fact_plus_use",
        "wegotrip_native": "short_fact_plus_use",
        "big_guide": "editorial_feature",
        "deep_guide": "editorial_feature",
    }
    return mapping.get(pillar, "editorial_feature")


def default_audience_axis(*, market: str, audience: str, pillar: str) -> str:
    if market == "en":
        if pillar in {"weekend_ideas", "weekend_plans", "exhibitions_museums"}:
            return "en_local"
        if pillar in {"trip_planning", "city_day_route", "short_routes"}:
            return "en_trip"
        return "en_culture"
    if pillar in {"weekend_ideas", "weekend_plans", "exhibitions_museums", "scenario_picks"}:
        if audience == "traveler":
            return "ru_domestic_trip"
        return "ru_local_leisure"
    if pillar in {"trip_planning"}:
        return "ru_outbound_trip" if audience == "traveler" else "ru_domestic_trip"
    return "culture_and_curiosity"


def default_channel_targets(market: str) -> list[str]:
    if market == "en":
        return ["telegram_en"]
    return ["telegram_ru", "max_ru"]


__all__ = [
    "AUDIENCE_AXES",
    "CHANNEL_IDS",
    "CULTURE_AXES",
    "CULTURE_MECHANICS",
    "EDITORIAL_MECHANICS",
    "INSTRUCTION_MECHANICS",
    "LIGHT_MECHANICS",
    "MECHANIC_SOURCES",
    "PRACTICAL_TRAVEL_AXES",
    "STORY_MECHANICS",
    "AudienceAxis",
    "ChannelId",
    "EditorialMechanic",
    "default_audience_axis",
    "default_channel_targets",
    "default_mechanic_for_pillar",
]
