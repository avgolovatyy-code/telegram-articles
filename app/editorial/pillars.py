"""Content pillars and post formats (spec §4–§5)."""

from __future__ import annotations

from dataclasses import dataclass

POST_FORMATS = frozenset(
    {
        "short_post",
        "story_post",
        "weekend_digest",
        "event_alert",
        "museum_spotlight",
        "city_micro_itinerary",
        "visual_carousel",
        "poll",
        "product_spotlight",
        "rich_guide",
    }
)

AUDIENCE_VALUES = frozenset({"local", "traveler", "both"})


@dataclass(frozen=True, slots=True)
class ContentPillar:
    code: str
    title_ru: str
    title_en: str
    default_formats: tuple[str, ...]


PILLARS: dict[str, ContentPillar] = {
    "weekend_ideas": ContentPillar(
        "weekend_ideas",
        "Куда сходить на выходных",
        "Weekend ideas",
        ("weekend_digest", "short_post"),
    ),
    "exhibitions_museums": ContentPillar(
        "exhibitions_museums",
        "Новые выставки и музеи",
        "Exhibitions & museums",
        ("event_alert", "museum_spotlight"),
    ),
    "travel_news": ContentPillar(
        "travel_news",
        "Travel news",
        "Travel news",
        ("event_alert", "short_post"),
    ),
    "city_day_route": ContentPillar(
        "city_day_route",
        "Город за день",
        "City in a day",
        ("city_micro_itinerary", "story_post"),
    ),
    "hidden_gem": ContentPillar(
        "hidden_gem",
        "Неочевидное место",
        "Hidden gem",
        ("story_post", "short_post"),
    ),
    "place_story": ContentPillar(
        "place_story",
        "История места",
        "Place story",
        ("story_post", "poll"),
    ),
    "museum_without_boredom": ContentPillar(
        "museum_without_boredom",
        "Музей без скуки",
        "Museum without boredom",
        ("museum_spotlight", "story_post"),
    ),
    "scenario_picks": ContentPillar(
        "scenario_picks",
        "С детьми / для двоих / бесплатно",
        "Scenario picks",
        ("weekend_digest", "short_post"),
    ),
    "trip_planning": ContentPillar(
        "trip_planning",
        "Планируем путешествие",
        "Trip planning",
        ("story_post", "rich_guide"),
    ),
    "fresh_angle": ContentPillar(
        "fresh_angle",
        "Неожиданный взгляд",
        "Fresh angle",
        ("poll", "visual_carousel"),
    ),
    "community_poll": ContentPillar(
        "community_poll",
        "Мнение / опрос",
        "Poll",
        ("poll",),
    ),
    "product_in_context": ContentPillar(
        "product_in_context",
        "Продукт WeGoTrip в контексте",
        "Product in context",
        ("product_spotlight", "story_post"),
    ),
    "big_guide": ContentPillar(
        "big_guide",
        "Большой путеводитель",
        "Big guide",
        ("rich_guide",),
    ),
}


def pillar_codes() -> list[str]:
    return list(PILLARS.keys())


__all__ = [
    "AUDIENCE_VALUES",
    "ContentPillar",
    "PILLARS",
    "POST_FORMATS",
    "pillar_codes",
]
