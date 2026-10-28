"""Native PostFormat payloads (spec §5 / §19.9)."""

from __future__ import annotations

import datetime as dt

from app.db.models import Article, EditorialPlanSlot
from app.editorial.formats import native_payload
from app.telegram.api import DryRunTelegramClient
from app.telegram.publisher import TelegramPublisher


def _article(session, *, market: str = "en") -> Article:
    article = Article(
        public_id="fmt-1",
        market=market,
        topic_slug="fmt",
        entity_type="city",
        entity_external_id="1",
        entity_name="Paris",
        intent="things_to_do",
        primary_query="weekend in paris",
        title="Where should we go this weekend?",
        body={
            "title": "Where should we go this weekend?",
            "intro": "A short poll for locals.",
            "sections": [
                {
                    "heading": "Pick one",
                    "blocks": [{"type": "list", "items": ["Louvre", "A park walk", "A day trip"]}],
                }
            ],
        },
        rendered_message={"blocks": []},
        current_version=1,
    )
    session.add(article)
    session.flush()
    return article


def test_poll_format_uses_send_poll(session):
    article = _article(session)
    session.add(
        EditorialPlanSlot(
            market="en",
            slot_date=dt.date.today(),
            pillar="community_poll",
            format="poll",
            audience="local",
            status="generated",
            article_id=article.id,
            payload={},
        )
    )
    session.flush()
    payload = native_payload(session, article)
    assert payload.method == "sendPoll"
    assert payload.question
    assert len(payload.options or []) >= 2


def test_short_post_uses_send_message(session):
    article = _article(session)
    session.add(
        EditorialPlanSlot(
            market="en",
            slot_date=dt.date.today(),
            pillar="weekend_ideas",
            format="short_post",
            audience="both",
            status="generated",
            article_id=article.id,
            payload={},
        )
    )
    session.flush()
    payload = native_payload(session, article)
    assert payload.method == "sendMessage"
    assert "weekend" in (payload.text or "").lower() or "Paris" in (payload.text or "")


def test_publisher_dispatches_poll(session, settings):
    article = _article(session)
    session.add(
        EditorialPlanSlot(
            market="en",
            slot_date=dt.date.today(),
            pillar="community_poll",
            format="poll",
            audience="local",
            status="generated",
            article_id=article.id,
            payload={},
        )
    )
    session.flush()
    client = DryRunTelegramClient(settings)
    publisher = TelegramPublisher(session, client, settings=settings)
    result = publisher.publish(article, article.rendered_message or {"blocks": []}, target="test")
    assert result.created
    assert client.sent
    assert "question" in client.sent[-1][1]
