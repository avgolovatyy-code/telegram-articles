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


def test_slots_stay_inside_the_publishing_window(session, settings):
    for index in range(6):
        make_article(session, "en", ArticleStatus.APPROVED, index)

    jobs.schedule_publications(session, markets=("en",), settings=settings)

    for article in session.scalars(select(Article).where(Article.scheduled_for.is_not(None))):
        hour = article.scheduled_for.hour
        assert settings.publish_window_start_hour <= hour <= settings.publish_window_end_hour


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
