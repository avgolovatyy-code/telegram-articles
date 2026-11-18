"""Independent Dzen calendar. Does not read Telegram/MAX slots as copy source."""

from __future__ import annotations

import datetime as dt
import json
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.prompts import PROMPTS
from app.ai.router import LLMGateway
from app.config import Settings, get_settings
from app.db.enums import DzenArticleStatus, DzenAudience, DzenFormat, DzenPillar, LLMTask
from app.db.models import City, DzenArticle, Product
from app.dzen.genre import genre_from_format
from app.dzen.policy import local_now, parse_weekdays
from app.dzen.schemas import DzenBrief, DzenDecisionSet, dzen_decision_json_schema
from app.logging_setup import get_logger

log = get_logger("dzen.planner")

# Illustrative first-month angles from the spec — validated against live inventory
# before an article is written. Not a promise that each venue is available today.
SEED_ANGLES = [
    (
        "Как российской картой оплатить билет в музей за границей: что проверить",
        DzenFormat.TRAVEL_HACK,
        DzenPillar.TRAVEL_HACKS,
        "Париж",
        "FR",
    ),
    (
        "Стамбул без гонки: маршрут между знакомыми местами и тихими кварталами",
        DzenFormat.CITY_GUIDE,
        DzenPillar.CITY_GUIDES,
        "Стамбул",
        "TR",
    ),
    (
        "Что посмотреть в Эрмитаже за два часа",
        DzenFormat.ATTRACTION_GUIDE,
        DzenPillar.MUSEUMS,
        "Санкт-Петербург",
        "RU",
    ),
    (
        "Барселона глазами архитекторов: Гауди и неожиданные альтернативы",
        DzenFormat.CULTURAL_FEATURE,
        DzenPillar.CITY_GUIDES,
        "Барселона",
        "ES",
    ),
    (
        "Выходные в Казани: кремль, слобода и вечер без обязательного Свияжска",
        DzenFormat.WEEKEND_ITINERARY,
        DzenPillar.WEEKEND_EVENTS,
        "Казань",
        "RU",
    ),
]


def upcoming_publish_dates(settings: Settings, *, start: dt.date, weeks: int = 2) -> list[dt.date]:
    wanted = parse_weekdays(settings.dzen_schedule_publish_days)
    dates: list[dt.date] = []
    cursor = start
    limit = start + dt.timedelta(weeks=weeks)
    while cursor <= limit:
        if cursor.weekday() in wanted:
            dates.append(cursor)
        cursor += dt.timedelta(days=1)
    return dates[: max(1, int(settings.dzen_articles_per_week)) * weeks]


def _existing_dates(session: Session, dates: list[dt.date]) -> set[dt.date]:
    if not dates:
        return set()
    rows = session.scalars(
        select(DzenArticle.planned_date).where(
            DzenArticle.planned_date.in_(dates),
            DzenArticle.status.notin_(
                [DzenArticleStatus.CANCELLED.value, DzenArticleStatus.BLOCKED.value]
            ),
        )
    )
    return {row for row in rows if row is not None}


def plan_dzen_week(
    session: Session,
    *,
    settings: Settings | None = None,
    gateway: LLMGateway | None = None,
    run_date: dt.date | None = None,
) -> list[DzenArticle]:
    settings = settings or get_settings()
    if not settings.dzen_enabled:
        return []
    local = local_now(settings)
    run_date = run_date or local.date()
    dates = upcoming_publish_dates(settings, start=run_date)
    taken = _existing_dates(session, dates)
    missing = [day for day in dates if day not in taken]
    if not missing:
        return []

    cities = list(
        session.scalars(
            select(City).where(City.market == "ru").order_by(City.popularity_rank).limit(40)
        )
    )
    foreign = [c for c in cities if (c.country_name or "").casefold() not in {"russia", "россия"}]
    domestic = [c for c in cities if c not in foreign]
    mixed = (foreign[:8] + domestic[:8]) or cities
    ru_products = session.scalar(
        select(func.count())
        .select_from(Product)
        .where(Product.market == "ru", Product.available.is_(True))
    )
    brief_payload = {
        "run_date": run_date.isoformat(),
        "needed_dates": [d.isoformat() for d in missing],
        "ru_product_count": int(ru_products or 0),
        "sample_cities": [
            {"name": c.name, "country": c.country_name, "country_id": c.country_external_id}
            for c in mixed[:16]
        ],
        "rule": (
            "independent Dzen magazine; mix Russia and abroad; vary formats; "
            "do not copy Telegram; do not plan neighbouring side-trip cities"
        ),
    }
    gateway = gateway or LLMGateway(session, settings=settings)
    parsed: dict = {}
    try:
        result = gateway.run(
            task=LLMTask.DZEN_CHIEF_EDITOR,
            prompt=PROMPTS["dzen_chief_editor_v1"],
            payload=json.dumps(brief_payload, ensure_ascii=False),
            json_schema=dzen_decision_json_schema(),
            schema_name="dzen_decision_set",
            market="ru",
            enforce_budget=True,
        )
        parsed = result.response.parsed if isinstance(result.response.parsed, dict) else {}
    except Exception as exc:
        log.warning("dzen.planner.llm_failed", error=str(exc))

    decision = DzenDecisionSet.model_validate(
        parsed or {"run_date": run_date.isoformat(), "briefs": []}
    )
    created: list[DzenArticle] = []
    for index, day in enumerate(missing):
        brief = _brief_for_day(decision, day, index, mixed)
        payload = json.loads(brief.model_dump_json())
        payload["genre"] = brief.genre or genre_from_format(brief.format)
        payload["reader_promise"] = brief.reader_promise or brief.reader_value
        article = DzenArticle(
            public_id=secrets.token_urlsafe(8),
            status=DzenArticleStatus.TOPIC_CANDIDATE.value,
            format=brief.format,
            pillar=brief.pillar,
            audience=brief.audience,
            planned_date=day,
            destination_country=(brief.destination_country or "")[:16] or None,
            destination_city=(brief.destination_city or "")[:128] or None,
            headline=brief.angle[:200],
            brief=payload,
        )
        session.add(article)
        created.append(article)
    session.flush()
    return created


def _brief_for_day(
    decision: DzenDecisionSet, day: dt.date, index: int, cities: list[City]
) -> DzenBrief:
    for item in decision.briefs:
        if item.planned_date == day.isoformat():
            return item
    if index < len(decision.briefs):
        item = decision.briefs[index]
        item.planned_date = day.isoformat()
        return item
    angle, fmt, pillar, city, country = SEED_ANGLES[index % len(SEED_ANGLES)]
    genre = genre_from_format(fmt.value)
    return DzenBrief(
        planned_date=day.isoformat(),
        format=fmt.value,
        pillar=pillar.value,
        audience=DzenAudience.RUSSIAN_SPEAKING_GLOBAL.value,
        destination_city=city,
        destination_country=country,
        angle=angle,
        reader_value="Практическая польза без обязательной покупки",
        reader_promise="Практическая польза без обязательной покупки",
        genre=genre,
        why_now="слот независимого плана Дзена",
        intent="independent_dzen",
    )


__all__ = ["plan_dzen_week", "upcoming_publish_dates"]
