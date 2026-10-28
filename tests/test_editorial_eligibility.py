"""Editorial spec cutoff and legacy backlog gates."""

from __future__ import annotations

import datetime as dt

from app.db.enums import ArticleStatus
from app.db.models import Article
from app.db.types import utcnow
from app.editorial.eligibility import article_meets_editorial_spec, publication_allowed
from app.scheduler import jobs
from app.services.workflow import ArticleWorkflow
from app.telegram.blocks import heading, paragraph, rich_message


def _article(session, *, created: dt.datetime | None = None) -> Article:
    article = Article(
        public_id="cutoff-test",
        market="ru",
        topic_slug="ru-topic",
        entity_type="city",
        entity_external_id="1",
        entity_name="Test",
        intent="things_to_do",
        primary_query="q",
        status=ArticleStatus.NEEDS_REVIEW,
        current_version=1,
        rendered_message=rich_message([heading("T", 1), paragraph("Body")]),
        body={"title": "T", "intro": "Body", "sections": []},
        products_refreshed_at=utcnow(),
    )
    if created is not None:
        article.created_at = created
    session.add(article)
    session.flush()
    return article


def test_pre_cutoff_article_blocked(settings, session, monkeypatch):
    monkeypatch.setattr(settings, "editorial_spec_cutoff_date", dt.date(2026, 10, 28))
    old = _article(session, created=dt.datetime(2026, 10, 1, tzinfo=dt.UTC))
    assert not article_meets_editorial_spec(old, settings)
    ok, reason = publication_allowed(old, settings, "production")
    assert not ok
    assert "EDITORIAL_SPEC_CUTOFF_DATE" in reason


def test_post_cutoff_article_allowed(settings, session, monkeypatch):
    monkeypatch.setattr(settings, "editorial_spec_cutoff_date", dt.date(2026, 10, 28))
    new = _article(session, created=dt.datetime(2026, 10, 28, 10, 0, tzinfo=dt.UTC))
    assert article_meets_editorial_spec(new, settings)


def test_schedule_skips_pre_cutoff(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "auto_publish_ru", True)
    monkeypatch.setattr(settings, "editorial_spec_cutoff_date", dt.date(2026, 10, 28))
    _article(session, created=dt.datetime(2026, 9, 1, tzinfo=dt.UTC))
    report = jobs.schedule_publications(session, markets=("ru",), settings=settings)
    assert report.details["ru_scheduled"] == 0


def test_legacy_scheduler_off_skips_generate_and_schedule(settings, session, monkeypatch):
    monkeypatch.setattr(settings, "old_article_auto_scheduler_enabled", False)
    gen = jobs.generate_daily_articles(session, markets=("ru",), settings=settings, max_per_run=1)
    assert gen.details.get("skipped") == "OLD_ARTICLE_AUTO_SCHEDULER_ENABLED=false"
    sched = jobs.schedule_publications(session, markets=("ru",), settings=settings)
    assert sched.details.get("skipped") == "OLD_ARTICLE_AUTO_SCHEDULER_ENABLED=false"


def test_workflow_publish_refuses_validation_failed(settings, session, monkeypatch):
    monkeypatch.setattr(settings, "editorial_spec_cutoff_date", None)
    monkeypatch.setattr(settings, "telegram_dry_run", True)
    article = _article(session)
    article.status = ArticleStatus.VALIDATION_FAILED
    session.flush()
    result = ArticleWorkflow(session, settings=settings).publish_test(article)
    assert not result.ok
