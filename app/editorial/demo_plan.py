"""Deterministic 30-day calendars and sample drafts for editorial review.

Dry-run artefacts only. Never published to production by this module.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.editorial.mechanics import EDITORIAL_MECHANICS
from app.editorial.pillars import PILLARS
from app.max.holidays import russia_calendar_context

PILLAR_CYCLE = list(PILLARS.keys())
FORMAT_CYCLE = [
    "weekend_digest",
    "story_post",
    "short_post",
    "museum_spotlight",
    "city_micro_itinerary",
    "poll",
    "event_alert",
    "visual_carousel",
    "product_spotlight",
    "rich_guide",
]


def _weekdays_for_cadence(start: dt.date, days: int, per_week: int) -> list[dt.date]:
    out: list[dt.date] = []
    # Prefer Mon/Tue/Wed/Thu/Sun patterns, skip filler Fridays when possible.
    preferred = {0, 1, 2, 3, 6}
    day = start
    week_count = 0
    week_start = start
    for _ in range(days):
        if day - week_start >= dt.timedelta(days=7):
            week_start = day
            week_count = 0
        if day.weekday() in preferred and week_count < per_week:
            out.append(day)
            week_count += 1
        day += dt.timedelta(days=1)
    return out


def build_channel_calendar(
    *,
    channel: str,
    start: dt.date,
    days: int = 30,
    per_week: int = 5,
) -> list[dict[str, Any]]:
    dates = _weekdays_for_cadence(start, days, per_week)
    slots: list[dict[str, Any]] = []
    for index, day in enumerate(dates):
        pillar = PILLAR_CYCLE[index % len(PILLAR_CYCLE)]
        mechanic = EDITORIAL_MECHANICS[index % len(EDITORIAL_MECHANICS)]
        fmt = FORMAT_CYCLE[index % len(FORMAT_CYCLE)]
        if fmt == "rich_guide" and index not in {8, 22}:
            fmt = "story_post"
        calendar = russia_calendar_context(day) if channel != "telegram_en" else None
        slots.append(
            {
                "date": day.isoformat(),
                "channel": channel,
                "pillar": pillar,
                "format": fmt,
                "editorial_mechanic": mechanic,
                "audience_axis": _axis(channel, mechanic),
                "product_recommendation": "none" if index % 5 else "optional",
                "holiday_label": calendar.label if calendar else "global",
                "why_now": _why_now(channel, mechanic, day),
            }
        )
    return slots


def _axis(channel: str, mechanic: str) -> str:
    if channel == "telegram_en":
        if mechanic == "weekend_utility":
            return "en_local"
        if mechanic == "practical_from_russia":
            return "en_trip"
        return "en_culture"
    if channel == "max_ru":
        if mechanic in {"practical_from_russia"}:
            return "ru_outbound_trip"
        if mechanic in {"weekend_utility", "short_fact_plus_use"}:
            return "ru_local_leisure"
        return "culture_and_curiosity"
    if mechanic == "practical_from_russia":
        return "ru_outbound_trip"
    if mechanic == "weekend_utility":
        return "ru_local_leisure"
    return "culture_and_curiosity"


def _why_now(channel: str, mechanic: str, day: dt.date) -> str:
    if mechanic == "weekend_utility":
        return f"Четверг/выходные {day.isoformat()}: локальный досуг, не всероссийская афиша"
    if mechanic == "practical_from_russia":
        return "Спрос на выезд из РФ есть в baseline АТОР, факты поездки — только после проверки"
    if mechanic == "curious_travel_news":
        return "Любопытная travel-история без продажи"
    return f"{channel}: механика {mechanic} для разнообразия ленты"


def build_three_channel_plan(start: dt.date | None = None) -> dict[str, Any]:
    start = start or dt.date(2026, 10, 29)
    return {
        "start": start.isoformat(),
        "horizon_days": 30,
        "note": "Демонстрационный план, не production-очередь. Пустые дни допустимы.",
        "telegram_ru": build_channel_calendar(channel="telegram_ru", start=start, per_week=5),
        "telegram_en": build_channel_calendar(channel="telegram_en", start=start, per_week=4),
        "max_ru": build_channel_calendar(channel="max_ru", start=start, per_week=3),
    }


SAMPLE_DRAFTS: list[dict[str, Any]] = [
    {
        "id": "ru-01",
        "channel": "telegram_ru",
        "pillar": "weekend_ideas",
        "mechanic": "weekend_utility",
        "format": "weekend_digest",
        "title": "Нижний на выходных: набережная, один музей и маршрут без суеты",
        "body": (
            "Если вы уже в Нижнем или доедете за пару часов — хватит одного ясного плана. "
            "Набережная, кремль сверху и один музей, который не требует целого дня. "
            "Даты уточняйте у площадки: мы не подставляем часы работы наугад."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Нижний Новгород — город на Волге с кремлём и набережной",
                "status": "stable",
                "source": "https://www.culture.ru/",
            }
        ],
    },
    {
        "id": "ru-02",
        "channel": "telegram_ru",
        "pillar": "hidden_gem",
        "mechanic": "surprising_place",
        "format": "story_post",
        "title": "В Казани есть прогулка, которая начинается не с открытки",
        "body": (
            "Большинство текстов про Казань стартуют с одной и той же площади. "
            "Интереснее другой вход: как кремль читается, если идти со стороны жилых улиц. "
            "Билет не обязателен, чтобы это заметить."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Казанский Кремль — объект культурного наследия в центре города",
                "status": "stable",
                "source": "https://kazan-kremlin.ru/",
            }
        ],
    },
    {
        "id": "ru-03",
        "channel": "telegram_ru",
        "pillar": "travel_news",
        "mechanic": "curious_travel_news",
        "format": "short_post",
        "title": "Парижский фасад, который все фотографируют и мало кто читает",
        "body": (
            "Это не призыв срочно покупать билет в Европу. Это история про то, "
            "как музейный фасад рассказывает больше, чем открытка. Логистику поездки "
            "из России мы здесь не обещаем — её нет в проверенных фактах этого черновика."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Лувр — публичный музей в Париже",
                "status": "stable",
                "source": "https://www.louvre.fr/en",
            }
        ],
    },
    {
        "id": "ru-04",
        "channel": "telegram_ru",
        "pillar": "museum_without_boredom",
        "mechanic": "short_fact_plus_use",
        "format": "museum_spotlight",
        "title": "Эрмитаж: три зала, если у вас всего час",
        "body": (
            "Не «успеть всё». Один короткий маршрут по крылу, который имеет смысл, "
            "если вы уже в Петербурге. Часы работы и цены билета в этот текст не ставим — "
            "они меняются и требуют свежей проверки перед публикацией."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Государственный Эрмитаж — музей в Санкт-Петербурге",
                "status": "stable",
                "source": "https://www.hermitagemuseum.org/",
            }
        ],
    },
    {
        "id": "ru-05",
        "channel": "telegram_ru",
        "pillar": "trip_planning",
        "mechanic": "practical_from_russia",
        "format": "story_post",
        "title": "Китай в осеннем спросе: что можно сказать, а чего нельзя",
        "body": (
            "По оценке АТОР для организованных туров октября Китай заметен, но это не "
            "весь выезд. В этом черновике нет фразы «виза не нужна» и нет обещания "
            "прямого рейса — без консульского первоисточника такие советы не публикуем."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Китай входил в топ пакетных направлений октября 2026 по оценке АТОР",
                "status": "sourced_segment",
                "source": "https://www.interfax-russia.ru/tourism/news/pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay",
            }
        ],
    },
    {
        "id": "ru-06",
        "channel": "telegram_ru",
        "pillar": "place_story",
        "mechanic": "culture_and_people",
        "format": "story_post",
        "title": "Почему тайский рынок интересен тем, кто не любит шопинг",
        "body": (
            "Рынок — это не витрина отелей. Это ритм города: еда, торг, запахи, "
            "короткие разговоры. Поездку «прямо сейчас» этот текст не продаёт."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Уличные рынки — устойчивая часть городской культуры Таиланда",
                "status": "evergreen_requires_local_detail",
                "source": "https://www.tourismthailand.org/",
            }
        ],
    },
    {
        "id": "ru-07",
        "channel": "telegram_ru",
        "pillar": "community_poll",
        "mechanic": "playful_interaction",
        "format": "poll",
        "title": "Какой город угадаете по трём странным деталям?",
        "body": "Опрос без товара и без визовой инструкции. Только проверенные факты.",
        "product": False,
        "claims": [],
    },
    {
        "id": "ru-08",
        "channel": "telegram_ru",
        "pillar": "big_guide",
        "mechanic": "editorial_feature",
        "format": "rich_guide",
        "title": "Петербург без обязательной программы: как выбрать один фокус дня",
        "body": (
            "Редкий большой материал. Не список «топ-10», а способ выбрать один район "
            "и не тратить день на переезды. Карточки WeGoTrip — только если уместны."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Санкт-Петербург — крупный культурный центр России",
                "status": "stable",
                "source": "https://www.culture.ru/",
            }
        ],
    },
    {
        "id": "ru-09",
        "channel": "telegram_ru",
        "pillar": "scenario_picks",
        "mechanic": "weekend_utility",
        "format": "short_post",
        "title": "Москва с детьми: один крытый план на сырой день",
        "body": "Не афиша на весь город. Одна понятная идея, если на улице слякоть.",
        "product": False,
        "claims": [],
    },
    {
        "id": "ru-10",
        "channel": "telegram_ru",
        "pillar": "fresh_angle",
        "mechanic": "surprising_place",
        "format": "visual_carousel",
        "title": "Калининград: не про янтарь в сувенирке, а про свет на набережной",
        "body": "Другой ракурс знакомого города. Без «секретного места, о котором никто не знает».",
        "product": False,
        "claims": [],
    },
    {
        "id": "ru-11",
        "channel": "telegram_ru",
        "pillar": "product_in_context",
        "mechanic": "short_fact_plus_use",
        "format": "product_spotlight",
        "title": "Аудиогид уместен, когда маршрут уже понятен",
        "body": (
            "Сначала идея прогулки, потом — если в каталоге WeGoTrip.ru есть подходящий "
            "товар — карточка с coupon=435. Нет товара — пост всё равно живой."
        ),
        "product": True,
        "claims": [],
    },
    {
        "id": "ru-12",
        "channel": "telegram_ru",
        "pillar": "exhibitions_museums",
        "mechanic": "short_fact_plus_use",
        "format": "event_alert",
        "title": "Выставка, у которой ещё не закончились даты — иначе не публикуем",
        "body": "Если дата уже прошла, слот пустой. «Успейте» без календаря нельзя.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-01",
        "channel": "telegram_en",
        "pillar": "weekend_ideas",
        "mechanic": "weekend_utility",
        "format": "weekend_digest",
        "title": "A Florence Saturday that is not the entire Uffizi",
        "body": (
            "One neighbourhood, a short loop, and a museum you can actually finish. "
            "No MAX footer. No Russia visa notes. Original English, not a translation."
        ),
        "product": False,
        "claims": [
            {
                "claim": "The Uffizi Galleries are in Florence",
                "status": "stable",
                "source": "https://www.uffizi.it/en",
            }
        ],
    },
    {
        "id": "en-02",
        "channel": "telegram_en",
        "pillar": "hidden_gem",
        "mechanic": "surprising_place",
        "format": "story_post",
        "title": "The London street that is more interesting than the postcard",
        "body": "A small observation, not a ticket window. Audio-guide language is not assumed.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-03",
        "channel": "telegram_en",
        "pillar": "travel_news",
        "mechanic": "curious_travel_news",
        "format": "short_post",
        "title": "A Tokyo detail travellers notice and guidebooks skip",
        "body": "Curiosity first. We do not invent opening hours.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-04",
        "channel": "telegram_en",
        "pillar": "city_day_route",
        "mechanic": "weekend_utility",
        "format": "city_micro_itinerary",
        "title": "Barcelona in a day without treating it as a checklist",
        "body": "Named stops from the catalogue only. Skip what you should skip.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-05",
        "channel": "telegram_en",
        "pillar": "place_story",
        "mechanic": "culture_and_people",
        "format": "story_post",
        "title": "Lisbon’s hills make more sense when you follow the tramless streets",
        "body": "People and terrain, not a discount code.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-06",
        "channel": "telegram_en",
        "pillar": "museum_without_boredom",
        "mechanic": "short_fact_plus_use",
        "format": "museum_spotlight",
        "title": "The Met: three rooms if you only have an hour",
        "body": "No invented ticket prices. Official site remains the source for hours.",
        "product": False,
        "claims": [
            {
                "claim": "The Metropolitan Museum of Art is in New York",
                "status": "stable",
                "source": "https://www.metmuseum.org/",
            }
        ],
    },
    {
        "id": "en-07",
        "channel": "telegram_en",
        "pillar": "community_poll",
        "mechanic": "playful_interaction",
        "format": "poll",
        "title": "Which city would you recognise from three odd facts?",
        "body": "A light post. No product.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-08",
        "channel": "telegram_en",
        "pillar": "big_guide",
        "mechanic": "editorial_feature",
        "format": "rich_guide",
        "title": "Rome without the obligatory sprint",
        "body": "Rare long piece. One focus, not twenty attractions.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-09",
        "channel": "telegram_en",
        "pillar": "trip_planning",
        "mechanic": "editorial_feature",
        "format": "story_post",
        "title": "First time in Kyoto: gardens before checklists",
        "body": "Independent global planning. Not a Russia-outbound briefing.",
        "product": False,
        "claims": [
            {
                "claim": "Kyoto is a major cultural destination in Japan",
                "status": "stable",
                "source": "https://kyoto.travel/en",
            }
        ],
    },
    {
        "id": "en-10",
        "channel": "telegram_en",
        "pillar": "fresh_angle",
        "mechanic": "surprising_place",
        "format": "visual_carousel",
        "title": "Amsterdam’s canals are obvious. The side streets are the story.",
        "body": "A different frame, not a secret-nobody-knows claim.",
        "product": False,
        "claims": [],
    },
    {
        "id": "en-11",
        "channel": "telegram_en",
        "pillar": "product_in_context",
        "mechanic": "short_fact_plus_use",
        "format": "product_spotlight",
        "title": "When a WeGoTrip audio tour actually helps the walk",
        "body": "Optional wegotrip.com card with coupon=435. No English-audio claim without proof.",
        "product": True,
        "claims": [],
    },
    {
        "id": "en-12",
        "channel": "telegram_en",
        "pillar": "scenario_picks",
        "mechanic": "weekend_utility",
        "format": "short_post",
        "title": "A rainy-day plan that names the place",
        "body": "Useful and specific. No motivational sign-off.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-01",
        "channel": "max_ru",
        "pillar": "weekend_ideas",
        "mechanic": "weekend_utility",
        "format": "weekend_digest",
        "title": "Казань на выходных: короткий план для тех, кто уже в городе",
        "body": (
            "MAX пишет для жителей России. Это не копия Telegram RU: короче, с другим крючком, "
            "с датами выходных. Футер на Telegram добавляет рендерер."
        ),
        "product": False,
        "claims": [],
    },
    {
        "id": "max-02",
        "channel": "max_ru",
        "pillar": "hidden_gem",
        "mechanic": "surprising_place",
        "format": "story_post",
        "title": "Екатеринбург: один неочевидный двор, если вы уже рядом",
        "body": "Регион не Москва и не Петербург. Без выдуманной выставки.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-03",
        "channel": "max_ru",
        "pillar": "travel_news",
        "mechanic": "curious_travel_news",
        "format": "short_post",
        "title": "Киото как история, а не как билет на рейс",
        "body": "Культурный сюжет для читателя в России. Практическую доступность не обещаем.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-04",
        "channel": "max_ru",
        "pillar": "museum_without_boredom",
        "mechanic": "short_fact_plus_use",
        "format": "museum_spotlight",
        "title": "Третьяковка: на что смотреть, если времени мало",
        "body": "Локальная польза. Часы работы — только из официального источника.",
        "product": False,
        "claims": [
            {
                "claim": "Третьяковская галерея — музей в Москве",
                "status": "stable",
                "source": "https://www.tretyakovgallery.ru/",
            }
        ],
    },
    {
        "id": "max-05",
        "channel": "max_ru",
        "pillar": "trip_planning",
        "mechanic": "practical_from_russia",
        "format": "story_post",
        "title": "Турция остаётся большой. Это не запрет писать про Азию.",
        "body": (
            "Пакетные продажи октября — отдельный metric_type. Без «виза не нужна». "
            "Если фактов по въезду нет — HOLD практической части."
        ),
        "product": False,
        "claims": [
            {
                "claim": "Турция — крупнейшая доля октябрьских пакетных туров АТОР 2026",
                "status": "sourced_segment",
                "source": "https://www.interfax-russia.ru/tourism/news/pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay",
            }
        ],
    },
    {
        "id": "max-06",
        "channel": "max_ru",
        "pillar": "place_story",
        "mechanic": "culture_and_people",
        "format": "story_post",
        "title": "Сочи зимой — не только лыжи",
        "body": "Внутренний сюжет. Без курортной рекламы.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-07",
        "channel": "max_ru",
        "pillar": "community_poll",
        "mechanic": "playful_interaction",
        "format": "poll",
        "title": "Куда ближе выбраться на 2–3 ночи?",
        "body": "Лёгкий опрос. РСТ отмечает короткие поездки как сценарий, не как квоту.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-08",
        "channel": "max_ru",
        "pillar": "city_day_route",
        "mechanic": "weekend_utility",
        "format": "city_micro_itinerary",
        "title": "Новосибирск за день: три точки без столичной копии",
        "body": "Региональная ротация MAX.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-09",
        "channel": "max_ru",
        "pillar": "fresh_angle",
        "mechanic": "surprising_place",
        "format": "short_post",
        "title": "Калининградский свет, а не янтарная витрина",
        "body": "Короче Telegram, другой заход.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-10",
        "channel": "max_ru",
        "pillar": "scenario_picks",
        "mechanic": "weekend_utility",
        "format": "short_post",
        "title": "Подмосковье на пару часов, если не хочется далеко",
        "body": "Local leisure для жителей РФ.",
        "product": False,
        "claims": [],
    },
    {
        "id": "max-11",
        "channel": "max_ru",
        "pillar": "product_in_context",
        "mechanic": "short_fact_plus_use",
        "format": "product_spotlight",
        "title": "Когда аудиогид с wegotrip.ru правда помогает",
        "body": "Товар с coupon=435 и utm_source=max, если он есть. Иначе — без CTA.",
        "product": True,
        "claims": [],
    },
    {
        "id": "max-12",
        "channel": "max_ru",
        "pillar": "exhibitions_museums",
        "mechanic": "short_fact_plus_use",
        "format": "event_alert",
        "title": "Региональный музей: только если даты ещё живые",
        "body": "Прошедшие выставки не анонсируем.",
        "product": False,
        "claims": [],
    },
]


def drafts_for(channel: str) -> list[dict[str, Any]]:
    return [row for row in SAMPLE_DRAFTS if row["channel"] == channel]


__all__ = [
    "SAMPLE_DRAFTS",
    "build_channel_calendar",
    "build_three_channel_plan",
    "drafts_for",
]
