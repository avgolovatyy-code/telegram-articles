"""Editorial v2.2 cadence wiring."""

from __future__ import annotations

import datetime as dt

from app.ai.budget import BudgetManager
from app.db.enums import ArticleStatus
from app.db.models import Article
from app.db.types import utcnow
from app.editorial.cadence import (
    effective_min_post_interval_minutes,
    production_posts_in_rolling_week,
    remaining_weekly_publish_slots,
)
from app.scheduler import jobs
from app.telegram.blocks import heading, paragraph, rich_message


def _article(session, market: str, *, status: str, scheduled: dt.datetime | None = None) -> Article:
    article = Article(
        public_id=f"cadence-{market}-{scheduled}",
        market=market,
        topic_slug=f"{market}-topic",
        entity_type="city",
        entity_external_id="1",
        entity_name="Test",
        intent="things_to_do",
        primary_query="q",
        status=status,
        current_version=1,
        rendered_message=rich_message([heading("T", 1), paragraph("Body")]),
        body={"title": "T", "intro": "Body", "sections": []},
        products_refreshed_at=utcnow(),
        scheduled_for=scheduled,
    )
    session.add(article)
    session.flush()
    return article


def test_v2_effective_min_interval_at_least_six_hours(settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "min_post_interval_minutes", 20)
    assert effective_min_post_interval_minutes(settings) == 360


def test_v2_caps_daily_generation_plan(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    plan = BudgetManager(session, settings).plan_daily_generation(session=session)
    assert plan["en"] <= settings.max_posts_per_day
    assert plan["ru"] <= settings.max_posts_per_day
    assert plan["en"] >= 1
    assert plan["ru"] >= 1


def test_v2_plan_ignores_unscheduled_drafts(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    _article(session, "en", status=ArticleStatus.NEEDS_REVIEW)
    _article(session, "ru", status=ArticleStatus.NEEDS_REVIEW)
    plan = BudgetManager(session, settings).plan_daily_generation(session=session)
    assert plan["en"] == 1
    assert plan["ru"] == 1


def test_weekly_hard_cap_blocks_schedule(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "editorial_v2_dry_run", False)
    monkeypatch.setattr(settings, "auto_publish_en", True)
    monkeypatch.setattr(settings, "max_posts_per_day", 2)
    monkeypatch.setattr(settings, "en_posts_per_week_hard_cap", 1)
    now = utcnow()
    _article(session, "en", status=ArticleStatus.SCHEDULED, scheduled=now)
    _article(session, "en", status=ArticleStatus.APPROVED)
    report = jobs.schedule_publications(session, markets=("en",), settings=settings)
    assert report.details["en_scheduled"] == 0
    assert "weekly" in report.details.get("en_note", "").lower()


def test_rolling_week_counts_scheduled(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    now = utcnow()
    _article(session, "ru", status=ArticleStatus.SCHEDULED, scheduled=now)
    assert production_posts_in_rolling_week(session, "ru", settings) == 1
    assert remaining_weekly_publish_slots(session, "ru", settings) == settings.ru_posts_per_week_hard_cap - 1
