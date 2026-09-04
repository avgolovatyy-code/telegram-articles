"""Scheduling, publication spacing and the mandatory test-channel pass."""

from __future__ import annotations

import datetime as dt
from itertools import pairwise

from sqlalchemy import select

from app.db.enums import ArticleStatus, PublicationStatus, PublicationTarget
from app.db.models import Article, PublicationQueueItem
from app.db.types import utcnow
from app.scheduler import jobs
from app.telegram.blocks import heading, paragraph, rich_message


def make_article(session, market: str, status: str, index: int = 0) -> Article:
    article = Article(
        public_id=f"sched-{market}-{index}",
        market=market,
        topic_slug=f"{market}-topic-{index}",
        entity_type="city",
        entity_external_id="2988507",
        entity_name="Paris" if market == "en" else "Париж",
        intent="things_to_do",
        primary_query="things to do in Paris",
        status=status,
        current_version=1,
        rendered_message=rich_message([heading("T", 1), paragraph("Body")]),
        body={"title": "T", "intro": "Body", "sections": []},
        products_refreshed_at=utcnow(),
    )
    session.add(article)
    session.flush()
    return article


def test_only_approved_articles_are_scheduled_in_review_mode(session, settings):
    make_article(session, "en", ArticleStatus.NEEDS_REVIEW, 1)
    approved = make_article(session, "en", ArticleStatus.APPROVED, 2)

    report = jobs.schedule_publications(session, markets=("en",), settings=settings)

    assert report.details["en_scheduled"] == 1
    assert approved.status == ArticleStatus.SCHEDULED


def test_auto_publish_picks_up_articles_awaiting_review(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "auto_publish_en", True)
    make_article(session, "en", ArticleStatus.NEEDS_REVIEW, 3)

    report = jobs.schedule_publications(session, markets=("en",), settings=settings)

    assert report.details["en_scheduled"] == 1


def test_a_test_publication_is_always_queued_before_production(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "auto_publish_en", True)
    article = make_article(session, "en", ArticleStatus.NEEDS_REVIEW, 4)

    jobs.schedule_publications(session, markets=("en",), settings=settings)

    targets = {
        item.target
        for item in session.scalars(
            select(PublicationQueueItem).where(PublicationQueueItem.article_id == article.id)
        )
    }
    assert targets == {PublicationTarget.TEST, PublicationTarget.PRODUCTION}


def test_publications_are_spaced_out(session, settings):
    for index in range(4):
        make_article(session, "ru", ArticleStatus.APPROVED, index)

    jobs.schedule_publications(session, markets=("ru",), settings=settings)

    slots = sorted(
        article.scheduled_for
        for article in session.scalars(select(Article).where(Article.scheduled_for.is_not(None)))
    )
    gaps = [(b - a).total_seconds() / 60 for a, b in pairwise(slots)]
    assert gaps
    assert all(gap >= settings.min_post_interval_minutes for gap in gaps)


def test_new_slots_ignore_far_future_backlog(session, settings):
    """A multi-day queue must not push new posts even further out."""
    future = utcnow() + dt.timedelta(days=5)
    stuck = make_article(session, "en", ArticleStatus.SCHEDULED, 100)
    stuck.scheduled_for = future
    session.flush()

    for index in range(3):
        make_article(session, "en", ArticleStatus.APPROVED, index)

    jobs.schedule_publications(session, markets=("en",), settings=settings)

    new_slots = sorted(
        article.scheduled_for
        for article in session.scalars(
            select(Article).where(
                Article.scheduled_for.is_not(None),
                Article.id != stuck.id,
            )
        )
    )
    assert len(new_slots) == 3
    assert all(slot < future for slot in new_slots)
    # New batch starts within the next couple of publishing days, not after the backlog.
    horizon = utcnow() + dt.timedelta(days=2)
    assert new_slots[0] <= horizon


def test_remaining_same_day_slots_are_zero_after_window(session, settings, monkeypatch):
    """After 21:00 Moscow there is no same-day production capacity left."""
    # 19:30 UTC = 22:30 MSK on a fixed date.
    after_hours = dt.datetime(2026, 9, 3, 19, 30, tzinfo=dt.UTC)
    monkeypatch.setattr(jobs, "utcnow", lambda: after_hours)
    assert jobs.remaining_same_day_publish_slots(session, "en", settings) == 0


def test_slots_stay_inside_the_moscow_publishing_window(session, settings):
    """Window hours are local to PUBLISH_TIMEZONE, not UTC."""
    assert settings.publish_timezone == "Europe/Moscow"
    for index in range(12):
        make_article(session, "en", ArticleStatus.APPROVED, index)

    jobs.schedule_publications(session, markets=("en",), settings=settings)

    for article in session.scalars(select(Article).where(Article.scheduled_for.is_not(None))):
        local_hour = article.scheduled_for.astimezone(settings.publish_tz).hour
        assert settings.publish_window_start_hour <= local_hour <= settings.publish_window_end_hour


def test_a_batch_is_spread_across_the_whole_window(session, settings):
    """A batch generated at once must trickle out, not fire back to back."""
    for index in range(10):
        make_article(session, "en", ArticleStatus.APPROVED, index)

    jobs.schedule_publications(session, markets=("en",), settings=settings)

    slots = sorted(
        article.scheduled_for
        for article in session.scalars(select(Article).where(Article.scheduled_for.is_not(None)))
    )
    assert len(slots) == 10
    span_hours = (slots[-1] - slots[0]).total_seconds() / 3600
    window_hours = settings.publish_window_end_hour - settings.publish_window_start_hour
    # The batch should occupy most of a publishing window, not a couple of hours.
    assert span_hours >= min(window_hours, 9 * settings.min_post_interval_minutes / 60) * 0.75


def test_everything_ready_is_scheduled_when_no_ceiling_is_set(session, settings):
    assert settings.publish_per_day("en") is None
    for index in range(25):
        make_article(session, "en", ArticleStatus.APPROVED, index)

    report = jobs.schedule_publications(session, markets=("en",), settings=settings)

    assert report.details["en_scheduled"] == 25


def test_an_explicit_quota_is_not_multiplied_by_repeated_runs(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "en_publish_per_day", 10)
    # Morning Moscow so the whole quota fits in today's window.
    monkeypatch.setattr(jobs, "utcnow", lambda: dt.datetime(2026, 9, 3, 7, 0, tzinfo=dt.UTC))
    for index in range(15):
        make_article(session, "en", ArticleStatus.APPROVED, index)

    first = jobs.schedule_publications(session, markets=("en",), settings=settings)
    second = jobs.schedule_publications(session, markets=("en",), settings=settings)

    total = first.details["en_scheduled"] + second.details["en_scheduled"]
    assert total <= 10
    assert second.details["en_scheduled"] == 0


def test_queue_publishes_due_items_once(session, settings):
    article = make_article(session, "ru", ArticleStatus.APPROVED, 9)
    jobs.schedule_publications(session, markets=("ru",), settings=settings)
    for item in session.scalars(select(PublicationQueueItem)):
        item.scheduled_for = utcnow() - dt.timedelta(minutes=1)
    session.flush()

    first = jobs.process_publication_queue(session, settings=settings, limit=10)
    second = jobs.process_publication_queue(session, settings=settings, limit=10)

    assert first.details["published"] >= 1
    assert second.details["published"] == 0
    assert article.status == ArticleStatus.PUBLISHED
    statuses = {item.status for item in session.scalars(select(PublicationQueueItem))}
    assert statuses == {PublicationStatus.PUBLISHED}
