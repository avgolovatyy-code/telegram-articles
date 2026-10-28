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

    weekly_used = production_posts_in_rolling_week(session, market, settings)
    weekly_max = posts_per_week_target_max(settings, market)

    return {
        "run_date": run_date.isoformat(),
        "market": market,
        "timezone": settings.publish_timezone,
        "planning_horizons_days": [2, 7, 30],
        "brand_voice_version": settings.editorial_voice_version,
        "candidate_signals": candidate_signals,
        "verified_facts": [],
        "events_and_exhibitions": [],
        "google_trends_signals": [],
        "holidays_and_weekends": holidays,
        "catalog_opportunities": [],
        "current_editorial_plan": current_editorial_plan,
        "published_posts_60d": published_posts_60d,
        "performance_summary": {},
        "locked_editorial_slots": [row for row in current_editorial_plan if row.get("locked")],
        "limits": {
            "weekly_target_min": (
                settings.ru_posts_per_week_min if market == "ru" else settings.en_posts_per_week_min
            ),
            "weekly_target_max": weekly_max,
            "weekly_used": weekly_used,
            "daily_max": settings.max_posts_per_day,
        },
        "budget_remaining_usd": None,
    }


__all__ = ["build_daily_brief"]
