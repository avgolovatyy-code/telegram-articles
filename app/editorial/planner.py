"""Apply and query Chief Editor calendar decisions."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings
from app.db.models import EditorialPlanSlot, EditorialRun, TopicCandidate
from app.db.types import utcnow
from app.editorial.cadence import remaining_weekly_publish_slots
from app.editorial.schemas import EditorialDecision, EditorialDecisionSet


def apply_decision_set(
    session: Session,
    *,
    market: Market,
    run_date: dt.date,
    decision_set: EditorialDecisionSet,
    brief: dict[str, Any],
    llm_run_id: int | None,
    settings: Settings,
    dry_run: bool,
) -> EditorialRun:
    run = EditorialRun(
        run_id=str(uuid.uuid4()),
        run_date=run_date,
        market=market,
        status="dry_run" if dry_run else "success",
        dry_run=dry_run,
        editorial_thesis=decision_set.editorial_thesis,
        daily_summary=decision_set.daily_summary,
        brief=brief,
        decisions=decision_set.model_dump(mode="json"),
        diff={},
        llm_run_id=llm_run_id,
    )
    session.add(run)
    session.flush()

    if dry_run:
        session.flush()
        return run

    applied = 0
    for decision in decision_set.decisions:
        if decision.action != "add":
            continue
        if not _decision_allowed(session, market, decision, settings):
            continue
        topic_id = _resolve_topic_id(session, market, decision.candidate_id)
        slot = EditorialPlanSlot(
            run_id=run.id,
            market=market,
            slot_date=decision.planned_date,
            topic_id=topic_id,
            candidate_id=decision.candidate_id,
            pillar=decision.pillar,
            format=decision.format,
            audience=decision.audience,
            angle=decision.angle,
            reader_value=decision.reader_value,
            priority=decision.priority,
            status="needs_review" if decision.needs_human_review else "planned",
            needs_human_review=decision.needs_human_review,
            payload=decision.model_dump(mode="json"),
        )
        session.add(slot)
        applied += 1
    run.applied_at = utcnow()
    run.diff = {"applied_slots": applied}
    session.flush()
    return run


def _resolve_topic_id(
    session: Session, market: Market, candidate_id: str | None
) -> int | None:
    if not candidate_id:
        return None
    try:
        topic_id = int(candidate_id)
    except ValueError:
        return None
    row = session.get(TopicCandidate, topic_id)
    if row is None or row.market != market:
        return None
    return topic_id


def _decision_allowed(
    session: Session, market: Market, decision: EditorialDecision, settings: Settings
) -> bool:
    if decision.action != "add":
        return False
    if decision.planned_date < utcnow().astimezone(settings.publish_tz).date():
        return False
    if decision.format == "rich_guide":
        if _rich_guides_this_month(session, market, settings) >= settings.max_longform_articles_per_month:
            return False
    week_room = remaining_weekly_publish_slots(session, market, settings, use_hard_cap=True)
    # Count planned slots in the same rolling week window when applying batch.
    if week_room <= 0:
        return False
    existing = session.scalar(
        select(EditorialPlanSlot.id).where(
            EditorialPlanSlot.market == market,
            EditorialPlanSlot.slot_date == decision.planned_date,
            EditorialPlanSlot.status.in_(("planned", "locked", "needs_review")),
        )
    )
    if existing is not None:
        return False
    return True


def _rich_guides_this_month(session: Session, market: Market, settings: Settings) -> int:
    local = utcnow().astimezone(settings.publish_tz)
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if local.month == 12:
        next_month = local.replace(year=local.year + 1, month=1, day=1)
    else:
        next_month = local.replace(month=local.month + 1, day=1)
    start = month_start.astimezone(dt.UTC)
    end = next_month.astimezone(dt.UTC)
    rows = session.scalars(
        select(EditorialPlanSlot).where(
            EditorialPlanSlot.market == market,
            EditorialPlanSlot.format == "rich_guide",
            EditorialPlanSlot.status.in_(("planned", "locked", "generated")),
        )
    ).all()
    count = 0
    for row in rows:
        day = dt.datetime.combine(row.slot_date, dt.time.min, tzinfo=settings.publish_tz)
        if start <= day.astimezone(dt.UTC) < end:
            count += 1
    return count


def slots_ready_for_generation(
    session: Session, market: Market, settings: Settings, *, limit: int = 3
) -> list[EditorialPlanSlot]:
    today = utcnow().astimezone(settings.publish_tz).date()
    horizon = today + dt.timedelta(days=2)
    rows = list(
        session.scalars(
            select(EditorialPlanSlot)
            .where(
                EditorialPlanSlot.market == market,
                EditorialPlanSlot.status == "planned",
                EditorialPlanSlot.needs_human_review.is_(False),
                EditorialPlanSlot.topic_id.is_not(None),
                EditorialPlanSlot.article_id.is_(None),
                EditorialPlanSlot.slot_date >= today,
                EditorialPlanSlot.slot_date <= horizon,
            )
            .order_by(EditorialPlanSlot.slot_date, EditorialPlanSlot.priority.desc())
            .limit(limit)
        ).all()
    )
    return rows


def mark_slot_generated(session: Session, slot: EditorialPlanSlot, article_id: int) -> None:
    slot.article_id = article_id
    slot.status = "generated"
    session.flush()


__all__ = [
    "apply_decision_set",
    "mark_slot_generated",
    "slots_ready_for_generation",
]
