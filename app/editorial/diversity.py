"""Diversity and commercial caps for Chief Editor slots (spec §3–§5, §10)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings
from app.db.models import EditorialPlanSlot, TopicCandidate
from app.editorial.schemas import EditorialDecision

ACTIVE_SLOT_STATUSES = ("planned", "locked", "needs_review", "generated")
HARD_SELL_FORMATS = frozenset({"product_spotlight"})


def week_window(planned_date: dt.date) -> tuple[dt.date, dt.date]:
    """Rolling 7-day window ending on ``planned_date`` (inclusive)."""
    return planned_date - dt.timedelta(days=6), planned_date


def active_slots_in_window(
    session: Session, market: Market, start: dt.date, end: dt.date
) -> list[EditorialPlanSlot]:
    return list(
        session.scalars(
            select(EditorialPlanSlot)
            .where(
                EditorialPlanSlot.market == market,
                EditorialPlanSlot.slot_date >= start,
                EditorialPlanSlot.slot_date <= end,
                EditorialPlanSlot.status.in_(ACTIVE_SLOT_STATUSES),
            )
            .order_by(EditorialPlanSlot.slot_date)
        ).all()
    )


def reject_reason(
    session: Session,
    market: Market,
    decision: EditorialDecision,
    settings: Settings,
    *,
    pending_same_batch: list[EditorialDecision] | None = None,
) -> str | None:
    """Return a human-readable reject reason, or None if the add is allowed."""
    if decision.action not in {"add", "replace"}:
        return None
    planned = decision.planned_date
    start, end = week_window(planned)
    existing = active_slots_in_window(session, market, start, end)
    pending = [
        item
        for item in (pending_same_batch or [])
        if item.action in {"add", "replace"} and start <= item.planned_date <= end
    ]

    hard_cap = (
        settings.ru_posts_per_week_hard_cap if market == "ru" else settings.en_posts_per_week_hard_cap
    )
    if len(existing) + len(pending) >= hard_cap:
        return f"weekly hard cap {hard_cap} reached"

    same_day = [row for row in existing if row.slot_date == planned]
    same_day_pending = [item for item in pending if item.planned_date == planned]
    if same_day or same_day_pending:
        return "day already has a planned slot"

    recent = [row for row in existing if row.slot_date < planned][-2:]
    if len(recent) == 2 and recent[0].pillar == recent[1].pillar == decision.pillar:
        return f"three consecutive {decision.pillar} pillars"
    if len(recent) == 2 and recent[0].format == recent[1].format == decision.format:
        return f"three consecutive {decision.format} formats"

    commercial = [
        row
        for row in existing
        if row.format in HARD_SELL_FORMATS
        or (row.payload or {}).get("product_recommendation") == "required"
    ]
    pending_commercial = [
        item
        for item in pending
        if item.format in HARD_SELL_FORMATS or item.product_recommendation == "required"
    ]
    is_commercial = (
        decision.format in HARD_SELL_FORMATS or decision.product_recommendation == "required"
    )
    if is_commercial and (commercial or pending_commercial):
        return "hard-sell already used this week"
    total = len(existing) + len(pending) + 1
    commercial_count = len(commercial) + len(pending_commercial) + (1 if is_commercial else 0)
    if total >= 4 and commercial_count / total > settings.max_commercial_post_share:
        return "commercial share above cap"

    if decision.format == "rich_guide":
        month_start = planned.replace(day=1)
        if planned.month == 12:
            month_end = planned.replace(year=planned.year + 1, month=1, day=1) - dt.timedelta(days=1)
        else:
            month_end = planned.replace(month=planned.month + 1, day=1) - dt.timedelta(days=1)
        guides = active_slots_in_window(session, market, month_start, month_end)
        guide_count = sum(1 for row in guides if row.format == "rich_guide")
        pending_guides = sum(1 for item in pending if item.format == "rich_guide")
        if guide_count + pending_guides + 1 > settings.max_longform_articles_per_month:
            return "rich_guide monthly cap"

    topic_id = _topic_id(decision.candidate_id)
    if topic_id is not None:
        topic = session.get(TopicCandidate, topic_id)
        if topic is not None:
            yesterday = planned - dt.timedelta(days=1)
            prior = [
                row
                for row in existing
                if row.slot_date == yesterday and row.topic_id is not None
            ]
            for row in prior:
                prior_topic = session.get(TopicCandidate, row.topic_id)
                if prior_topic is not None and prior_topic.entity_name == topic.entity_name:
                    return f"same city {topic.entity_name} two days in a row"
    return None


def _topic_id(candidate_id: str | None) -> int | None:
    if not candidate_id:
        return None
    try:
        return int(candidate_id)
    except ValueError:
        return None


__all__ = [
    "ACTIVE_SLOT_STATUSES",
    "HARD_SELL_FORMATS",
    "reject_reason",
    "week_window",
]
