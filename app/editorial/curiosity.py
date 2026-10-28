"""Culture / curiosity candidates so demand signals cannot flatten the feed."""

from __future__ import annotations

from typing import Any

from app.max.holidays import russia_calendar_context

#: Evergreen, sourced cultural hooks. Not live news; Writer still VERIFY OR OMIT.
CULTURE_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "id": "kyoto-temple-gardens",
        "geo": "JP",
        "city": "Kyoto",
        "audience_axis": "culture_and_curiosity",
        "editorial_mechanic": "curious_travel_news",
        "angle_ru": "Почему сады храмов Киото читаются как история города, даже если вы не едете",
        "angle_en": "Temple gardens in Kyoto as a way to read the city — no ticket pitch",
        "why_worth_reading_without_purchase": "A cultural curiosity, not a booking prompt",
        "source_name": "Kyoto City Official Travel Guide",
        "source_url": "https://kyoto.travel/en",
        "status": "evergreen_requires_verification",
    },
    {
        "id": "paris-museum-facade",
        "geo": "FR",
        "city": "Paris",
        "audience_axis": "culture_and_curiosity",
        "editorial_mechanic": "editorial_feature",
        "angle_ru": "Что скрывается за фасадом парижского музея — без совета срочно лететь",
        "angle_en": "What a familiar Paris museum façade is actually telling you",
        "why_worth_reading_without_purchase": "Architecture story, logistics omitted",
        "source_name": "Musée du Louvre",
        "source_url": "https://www.louvre.fr/en",
        "status": "evergreen_requires_verification",
    },
    {
        "id": "kazan-kremlin-unesco",
        "geo": "RU",
        "city": "Казань",
        "audience_axis": "ru_local_leisure",
        "editorial_mechanic": "short_fact_plus_use",
        "angle_ru": "Казанский Кремль: один факт, который меняет прогулку по центру",
        "angle_en": "One detail that changes a walk through the Kazan Kremlin",
        "why_worth_reading_without_purchase": "Local discovery, product optional",
        "source_name": "Казанский Кремль",
        "source_url": "https://kazan-kremlin.ru/",
        "status": "evergreen_requires_verification",
    },
    {
        "id": "nn-weekend-volga",
        "geo": "RU",
        "city": "Нижний Новгород",
        "audience_axis": "ru_local_leisure",
        "editorial_mechanic": "weekend_utility",
        "angle_ru": "Выходные в Нижнем: набережная, один музей и маршрут без суеты Москвы",
        "angle_en": "A Nizhny Novgorod weekend that is not a Moscow copy",
        "why_worth_reading_without_purchase": "Concrete local leisure",
        "source_name": "Культура.РФ",
        "source_url": "https://www.culture.ru/",
        "status": "evergreen_requires_verification",
    },
    {
        "id": "tutu-style-food-story",
        "geo": "TH",
        "city": "Bangkok",
        "audience_axis": "culture_and_curiosity",
        "editorial_mechanic": "culture_and_people",
        "angle_ru": "Почему уличные рынки Бангкока интересны тем, кто не любит шопинг",
        "angle_en": "Why Bangkok markets are interesting even if you hate shopping",
        "why_worth_reading_without_purchase": "People and food, not a hotel vitrine",
        "source_name": "Tourism Authority of Thailand",
        "source_url": "https://www.tourismthailand.org/",
        "status": "evergreen_requires_verification",
    },
    {
        "id": "playful-city-quiz",
        "geo": "WORLD",
        "city": None,
        "audience_axis": "culture_and_curiosity",
        "editorial_mechanic": "playful_interaction",
        "angle_ru": "Угадайте город по трём странным деталям — без визовой инструкции",
        "angle_en": "Guess the city from three odd details",
        "why_worth_reading_without_purchase": "Light engagement, no product",
        "source_name": "editorial",
        "source_url": None,
        "status": "needs_verified_facts_per_clue",
    },
)


def curiosity_candidates(*, market: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in CULTURE_CANDIDATES:
        row = dict(item)
        row["angle"] = row["angle_en"] if market == "en" else row["angle_ru"]
        out.append(row)
    return out


def events_for_brief(run_date) -> dict[str, Any]:
    calendar = russia_calendar_context(run_date)
    return {
        "provider": "RussiaEventsProvider",
        "status": "PARTIAL",
        "note": (
            "Живая афиша музеев не подключена легальным API; не выдумывать выставки. "
            "Используем календарь РФ и evergreen-кандидаты с VERIFY OR OMIT."
        ),
        "holidays_and_weekends": [
            {
                "date": calendar.date.isoformat(),
                "label": calendar.label,
                "is_weekend": calendar.is_weekend,
                "is_fixed_holiday": calendar.is_fixed_holiday,
                "is_leisure_priority_day": calendar.is_leisure_priority_day,
            }
        ],
        "museum_exhibitions": [],
        "regional_events": [],
        "blocked_sources": ["live_museum_feeds"],
    }


__all__ = ["CULTURE_CANDIDATES", "curiosity_candidates", "events_for_brief"]
