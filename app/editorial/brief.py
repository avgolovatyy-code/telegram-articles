"""Assemble DailyEditorialBrief from real DB signals (spec §6.4a)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings
from app.db.enums import ArticleStatus, TopicStatus
from app.db.models import Article, EditorialPlanSlot, TopicCandidate
from app.db.types import utcnow
from app.editorial.cadence import posts_per_week_target_max, production_posts_in_rolling_week
from app.editorial.curiosity import curiosity_candidates, events_for_brief
from app.editorial.mechanics import EDITORIAL_MECHANICS
from app.editorial.pillars import POST_FORMATS, pillar_codes
from app.editorial.russia_demand import RussiaDemandProvider
from app.editorial.sources import sources_for_market
from app.max.holidays import russia_calendar_context


def build_daily_brief(
    session: Session, market: Market, settings: Settings, *, run_date: dt.date | None = None
) -> dict[str, Any]:
    run_date = run_date or utcnow().astimezone(settings.publish_tz).date()
    candidates = list(
        session.scalars(
            select(TopicCandidate)
            .where(
                TopicCandidate.market == market,
                TopicCandidate.status == TopicStatus.CANDIDATE,
            )
            .order_by(TopicCandidate.topic_score.desc())
            .limit(40)
        ).all()
    )
    candidate_signals = [
        {
            "id": str(row.id),
            "entity_type": row.entity_type,
            "entity_name": row.entity_name,
            "primary_query": row.primary_query,
            "topic_score": row.topic_score,
            "intent": row.intent,
        }
        for row in candidates
    ]

    since = utcnow() - dt.timedelta(days=60)
    published = list(
        session.scalars(
            select(Article)
            .where(
                Article.market == market,
                Article.status == ArticleStatus.PUBLISHED,
                Article.published_at >= since,
            )
            .order_by(Article.published_at.desc())
            .limit(40)
        ).all()
    )
    published_posts_60d = [
        {
            "article_id": row.id,
            "title": row.title or row.primary_query,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "entity_name": row.entity_name,
        }
        for row in published
    ]

    horizon_end = run_date + dt.timedelta(days=30)
    current_plan = list(
        session.scalars(
            select(EditorialPlanSlot)
            .where(
                EditorialPlanSlot.market == market,
                EditorialPlanSlot.status.in_(("planned", "locked")),
                EditorialPlanSlot.slot_date >= run_date,
                EditorialPlanSlot.slot_date <= horizon_end,
            )
            .order_by(EditorialPlanSlot.slot_date)
        ).all()
    )
    current_editorial_plan = [
        {
            "slot_id": row.id,
            "slot_date": row.slot_date.isoformat(),
            "pillar": row.pillar,
            "format": row.format,
            "audience": row.audience,
            "editorial_mechanic": row.editorial_mechanic,
            "audience_axis": row.audience_axis,
            "channel_targets": row.channel_targets or [],
            "destination_country": row.destination_country,
            "destination_city": row.destination_city,
            "locked": row.locked,
            "topic_id": row.topic_id,
            "priority": row.priority,
        }
        for row in current_plan
    ]

    holidays: list[dict[str, Any]] = []
    if market == "ru":
        ctx = russia_calendar_context(run_date)
        holidays.append(
            {
                "date": run_date.isoformat(),
                "label": ctx.label,
                "is_weekend": ctx.is_weekend,
                "is_fixed_holiday": ctx.is_fixed_holiday,
            }
        )
    else:
        holidays.append(
            {
                "date": run_date.isoformat(),
                "label": "weekend" if run_date.weekday() >= 5 else "weekday",
                "is_weekend": run_date.weekday() >= 5,
                "is_fixed_holiday": False,
            }
        )

    weekly_used = production_posts_in_rolling_week(session, market, settings)
    weekly_max = posts_per_week_target_max(settings, market)

    russia_brief: dict[str, Any] | None = None
    if market == "ru":
        demand = RussiaDemandProvider(session).brief_payload(as_of=run_date)
        events = events_for_brief(run_date)
        russia_brief = {
            "as_of": f"{run_date.isoformat()}T00:00:00+03:00",
            "market": "telegram_ru",
            "audience_origin_focus": "Russia",
            "readership": ["local", "traveler", "culture_curiosity"],
            "domestic_demand_signals": demand["domestic_demand_signals"],
            "outbound_demand_signals": demand["outbound_demand_signals"],
            "cultural_and_travel_curiosities": curiosity_candidates(market="ru"),
            "museum_exhibitions": events["museum_exhibitions"],
            "regional_events": events["regional_events"],
            "holidays_and_weekends": events["holidays_and_weekends"],
            "entry_and_transport_changes": [],
            "available_wegotrip_products": [],
            "recent_publications": published_posts_60d[:20],
            "pillar_distribution_30d": _distribution(current_plan, "pillar"),
            "geo_distribution_30d": _geo_distribution(current_plan),
            "editorial_mechanic_distribution_30d": _distribution(
                current_plan, "editorial_mechanic"
            ),
            "content_performance": {},
            "human_override_rules": [
                "Не трактовать доли пакетных туров как все поездки.",
                "Культурные истории без практического совета не штрафовать за логистику.",
                "MAX — жители России; Telegram RU шире.",
            ],
            "source_ledger": [
                {
                    "id": row.get("id"),
                    "url": row.get("source_url"),
                    "metric_type": row.get("metric_type"),
                    "caveat": row.get("caveat"),
                }
                for row in demand["domestic_demand_signals"] + demand["outbound_demand_signals"]
            ],
            "missing_live_trends": demand["missing_live_trends"],
        }

    localization = {
        "content_language": "ru" if market == "ru" else "en",
        "channel_id": "telegram_ru" if market == "ru" else "telegram_en",
        "editorial_market": ("ru_speaking_global" if market == "ru" else "international"),
        "audience_origin_context": "russia" if market == "ru" else "global",
        "max_channel": {
            "channel_id": "max_ru",
            "editorial_market": "residents_of_russia",
            "soft_mix": "75 local-domestic / 25 outbound from RU, culture not forced out",
            "include_in_ru_decisions": market == "ru",
        },
    }

    return {
        "run_date": run_date.isoformat(),
        "market": market,
        "timezone": settings.publish_timezone,
        "planning_horizons_days": [2, 7, 30],
        "brand_voice_version": settings.editorial_voice_version,
        "localization": localization,
        "candidate_signals": candidate_signals,
        "verified_facts": [],
        "source_registry": sources_for_market(market),
        "allowed_pillars": pillar_codes(),
        "allowed_formats": sorted(POST_FORMATS),
        "allowed_editorial_mechanics": list(EDITORIAL_MECHANICS),
        "cultural_and_travel_curiosities": curiosity_candidates(market=market),
        "events_and_exhibitions": events_for_brief(run_date)
        if market == "ru"
        else {
            "provider": "InternationalEventsProvider",
            "status": "PARTIAL",
            "note": (
                "Live museum/event feeds are not connected; VERIFY OR OMIT. "
                "Do not invent exhibitions or opening hours."
            ),
            "museum_exhibitions": [],
            "regional_events": [],
            "blocked_sources": ["live_museum_feeds"],
        },
        "google_trends_signals": {
            "status": "UNAVAILABLE",
            "note": "Нет авторизованного Trends коннектора; не выдумывать объёмы",
        },
        "holidays_and_weekends": holidays,
        "catalog_opportunities": [],
        "current_editorial_plan": current_editorial_plan,
        "published_posts_60d": published_posts_60d,
        "performance_summary": {},
        "locked_editorial_slots": [row for row in current_editorial_plan if row.get("locked")],
        "russia_editorial_market_brief": russia_brief,
        "limits": {
            "weekly_target_min": (
                settings.ru_posts_per_week_min if market == "ru" else settings.en_posts_per_week_min
            ),
            "weekly_target_max": weekly_max,
            "weekly_used": weekly_used,
            "daily_max": settings.max_posts_per_day,
            "max_posts_per_week_min": settings.maxapp_posts_per_week_min,
            "max_posts_per_week_max": settings.maxapp_posts_per_week_max,
        },
        "budget_remaining_usd": None,
    }


def _distribution(slots: list[EditorialPlanSlot], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in slots:
        key = getattr(row, field, None) or "unknown"
        counts[str(key)] = counts.get(str(key), 0) + 1
    return counts


def _geo_distribution(slots: list[EditorialPlanSlot]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in slots:
        key = row.destination_city or row.destination_country or "unspecified"
        counts[str(key)] = counts.get(str(key), 0) + 1
    return counts


__all__ = ["build_daily_brief"]
