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
from app.editorial.diversity import reject_reason
from app.editorial.schemas import EditorialDecision, EditorialDecisionSet

ACTIVE_STATUSES = ("planned", "locked", "needs_review", "generated")


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
    """Persist the calendar.

    ``dry_run`` records the run as dry and never publishes; slots still land in
    the 30-day plan so admin preview and diversity work. Generation of drafts is
    allowed; production enqueue is gated separately.
    """
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

    applied = 0
    dropped = 0
    moved = 0
    kept = 0
    skipped: list[str] = []
    accepted_adds: list[EditorialDecision] = []

    for decision in decision_set.decisions:
        if decision.action == "keep":
            kept += 1
            continue
        if decision.action == "skip" or decision.action == "request_research":
            skipped.append(f"{decision.action}:{decision.candidate_id or decision.slot_id}")
            continue
        if decision.action == "drop":
            if _drop_slot(session, market, decision.slot_id):
                dropped += 1
            continue
        if decision.action == "move":
            if _move_slot(session, market, decision):
                moved += 1
            continue
        if decision.action == "replace":
            _drop_slot(session, market, decision.slot_id)
            dropped += 1
        if decision.action in {"add", "replace"}:
            reason = reject_reason(
                session, market, decision, settings, pending_same_batch=accepted_adds
            )
            if reason:
                skipped.append(f"{decision.planned_date}:{reason}")
                continue
            if decision.planned_date < run_date:
                skipped.append(f"{decision.planned_date}:past date")
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
            accepted_adds.append(decision)

    run.applied_at = utcnow()
    run.diff = {
        "applied_slots": applied,
        "dropped": dropped,
        "moved": moved,
        "kept": kept,
        "skipped": skipped[:40],
        "empty_slots_justification": list(decision_set.empty_slots_justification),
    }
    session.flush()
    return run


def last_valid_run(session: Session, market: Market) -> EditorialRun | None:
    return session.scalar(
        select(EditorialRun)
        .where(
            EditorialRun.market == market,
            EditorialRun.status.in_(("success", "dry_run")),
        )
        .order_by(EditorialRun.created_at.desc())
        .limit(1)
    )


def _drop_slot(session: Session, market: Market, slot_id: int | None) -> bool:
    if slot_id is None:
        return False
    slot = session.get(EditorialPlanSlot, slot_id)
    if slot is None or slot.market != market or slot.locked:
        return False
    slot.status = "dropped"
    session.flush()
    return True


def _move_slot(session: Session, market: Market, decision: EditorialDecision) -> bool:
    if decision.slot_id is None:
        return False
    slot = session.get(EditorialPlanSlot, decision.slot_id)
    if slot is None or slot.market != market or slot.locked:
        return False
    slot.slot_date = decision.planned_date
    session.flush()
    return True


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


def set_slot_locked(session: Session, slot: EditorialPlanSlot, locked: bool) -> None:
    slot.locked = locked
    if locked and slot.status == "planned":
        slot.status = "locked"
    elif not locked and slot.status == "locked":
        slot.status = "planned"
    session.flush()


def skip_slot(session: Session, slot: EditorialPlanSlot) -> None:
    if slot.locked:
        return
    slot.status = "skipped"
    session.flush()


__all__ = [
    "apply_decision_set",
    "last_valid_run",
    "mark_slot_generated",
    "set_slot_locked",
    "skip_slot",
    "slots_ready_for_generation",
]
