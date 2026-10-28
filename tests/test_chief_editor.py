"""Chief Editor structured planning."""

from __future__ import annotations

from sqlalchemy import select

from app.db.enums import TopicStatus
from app.db.models import EditorialPlanSlot, EditorialRun, TopicCandidate
from app.scheduler import jobs


def _topic(session, market: str = "ru") -> TopicCandidate:
    row = TopicCandidate(
        market=market,
        topic_key=f"{market}-chief-test",
        topic_slug=f"{market}-chief-test",
        entity_type="city",
        entity_external_id="1",
        entity_name="Test City",
        intent="things_to_do",
        primary_query="куда сходить",
        canonical_query="куда сходить",
        topic_score=0.9,
        status=TopicStatus.CANDIDATE,
    )
    session.add(row)
    session.flush()
    return row


def test_chief_editor_creates_run_and_slot(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "editorial_v2_dry_run", False)
    monkeypatch.setattr(settings, "openai_chief_editor_daily", True)
    topic = _topic(session)
    report = jobs.run_chief_editor(session, markets=("ru",), settings=settings)
    assert report.ok
    assert report.details.get("ru_status") == "success"
    runs = list(session.scalars(select(EditorialRun).where(EditorialRun.market == "ru")))
    assert runs
    slots = list(session.scalars(select(EditorialPlanSlot).where(EditorialPlanSlot.market == "ru")))
    assert slots
    assert slots[0].topic_id == topic.id


def test_chief_editor_skipped_when_v2_off(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", False)
    report = jobs.run_chief_editor(session, settings=settings)
    assert report.details.get("skipped") == "EDITORIAL_V2_ENABLED=false"
