"""Slack: signature verification, buttons, commands and notifications."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app.config import Settings
from app.db.enums import ArticleStatus
from app.db.models import Article
from app.slack import blocks as sb
from app.slack.client import NullSlackClient
from app.slack.commands import CommandHandler
from app.slack.interactions import (
    MAX_REQUEST_AGE_SECONDS,
    InteractionHandler,
    verify_signature,
)
from app.slack.notifications import SlackNotifier
from app.telegram.blocks import heading, paragraph, rich_message

SECRET = "s3cr3t-signing-key"


def sign(body: bytes, timestamp: str, secret: str = SECRET) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()


def make_article(session, market: str = "en", status: str = ArticleStatus.NEEDS_REVIEW) -> Article:
    article = Article(
        public_id=f"slack-{market}-{status}",
        market=market,
        topic_slug="t",
        entity_type="city",
        entity_external_id="1",
        entity_name="Paris",
        intent="things_to_do",
        primary_query="things to do in Paris",
        title="Things to Do in Paris",
        status=status,
        current_version=1,
        char_count=4200,
        actual_cost_usd=0.0523,
        quality_score=0.93,
        factuality_score=0.99,
        body={"title": "Things to Do in Paris", "intro": "Start at the Pantheon.", "sections": []},
        rendered_message=rich_message([heading("T", 1), paragraph("Body")]),
    )
    session.add(article)
    session.flush()
    return article


# ----------------------------------------------------------------- signatures
def test_valid_signature_is_accepted():
    body = b"token=x&text=status"
    timestamp = str(int(time.time()))
    assert verify_signature(
        signing_secret=SECRET, timestamp=timestamp, body=body, signature=sign(body, timestamp)
    )


def test_signature_from_another_secret_is_rejected():
    body = b"token=x"
    timestamp = str(int(time.time()))
    assert not verify_signature(
        signing_secret=SECRET,
        timestamp=timestamp,
        body=body,
        signature=sign(body, timestamp, "someone-elses-secret"),
    )


def test_replayed_request_is_rejected():
    body = b"token=x"
    old = str(int(time.time()) - MAX_REQUEST_AGE_SECONDS - 60)
    assert not verify_signature(
        signing_secret=SECRET, timestamp=old, body=body, signature=sign(body, old)
    )


def test_tampered_body_is_rejected():
    timestamp = str(int(time.time()))
    signature = sign(b"text=status", timestamp)
    assert not verify_signature(
        signing_secret=SECRET, timestamp=timestamp, body=b"text=publish", signature=signature
    )


def test_missing_pieces_are_rejected():
    assert not verify_signature(signing_secret="", timestamp="1", body=b"", signature="v0=x")
    assert not verify_signature(signing_secret=SECRET, timestamp="", body=b"", signature="v0=x")
    assert not verify_signature(signing_secret=SECRET, timestamp="nope", body=b"", signature="v0=x")


# ------------------------------------------------------------------- buttons
def payload_for(action_id: str, article_id: int) -> dict:
    return {
        "user": {"username": "editor"},
        "actions": [{"action_id": action_id, "value": str(article_id)}],
    }


def test_reject_button_takes_the_article_down(session, settings):
    article = make_article(session)
    result = InteractionHandler(session, settings).handle(payload_for(sb.ACTION_REJECT, article.id))
    assert result.ok
    assert article.status == ArticleStatus.REJECTED
    assert "editor" in (article.status_reason or "")


def test_publish_test_button_publishes_to_the_test_channel(session, settings):
    article = make_article(session)
    result = InteractionHandler(session, settings).handle(
        payload_for(sb.ACTION_PUBLISH_TEST, article.id)
    )
    assert result.ok
    assert {p.target for p in article.publications} == {"test"}


def test_publish_button_goes_to_production(session, settings):
    article = make_article(session, status=ArticleStatus.APPROVED)
    result = InteractionHandler(session, settings).handle(
        payload_for(sb.ACTION_PUBLISH, article.id)
    )
    assert result.ok
    assert article.status == ArticleStatus.PUBLISHED


def test_unknown_article_is_reported(session, settings):
    result = InteractionHandler(session, settings).handle(payload_for(sb.ACTION_PUBLISH, 99999))
    assert not result.ok
    assert "не найдена" in result.text


def test_payload_without_actions_is_reported(session, settings):
    result = InteractionHandler(session, settings).handle({"user": {}})
    assert not result.ok


# ------------------------------------------------------------------ commands
def test_status_command_reports_budget_and_mode(session, settings):
    response = CommandHandler(session, settings).handle("status")
    text = json.dumps(response, ensure_ascii=False)
    assert "Бюджет" in text
    assert "Автопубликация" in text


def test_coverage_command_reports_remaining_material(synced_session, settings):
    response = CommandHandler(synced_session, settings).handle("coverage")
    assert "осталось тем" in json.dumps(response, ensure_ascii=False)


def test_pending_command_lists_scheduled_articles(session, settings):
    make_article(session, status=ArticleStatus.SCHEDULED)
    response = CommandHandler(session, settings).handle("pending")
    assert "Ожидают публикации" in json.dumps(response, ensure_ascii=False)


def test_unknown_command_shows_help(session, settings):
    response = CommandHandler(session, settings).handle("frobnicate")
    assert "Неизвестная команда" in json.dumps(response, ensure_ascii=False)


# -------------------------------------------------------------- notifications
def test_notifier_is_silent_when_slack_is_off(session, settings):
    notifier = SlackNotifier(session, settings, client=NullSlackClient(settings))
    assert not notifier.enabled
    notifier.article_drafted(make_article(session))
    assert notifier.client.sent == []


def test_notifier_sends_when_configured(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "slack_enabled", True)
    monkeypatch.setattr(settings, "slack_channel", "#content")
    client = NullSlackClient(settings)
    notifier = SlackNotifier(session, settings, client=client)

    notifier.article_drafted(make_article(session))

    assert len(client.sent) == 1
    assert "Things to Do in Paris" in client.sent[0][1]


def test_a_broken_slack_never_breaks_the_pipeline(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "slack_enabled", True)
    monkeypatch.setattr(settings, "slack_channel", "#content")

    class ExplodingClient(NullSlackClient):
        def post_message(self, **kwargs):
            raise RuntimeError("slack is down")

    notifier = SlackNotifier(session, settings, client=ExplodingClient(settings))
    notifier.article_drafted(make_article(session))  # must not raise


def test_digest_summarises_budget_and_coverage(synced_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "slack_enabled", True)
    monkeypatch.setattr(settings, "slack_channel", "#content")
    client = NullSlackClient(settings)

    SlackNotifier(synced_session, settings, client=client).daily_digest()

    assert client.sent
    assert client.sent[0][1] == "Сводка за день"


# ------------------------------------------------------------------- defaults
def test_auto_publish_is_on_by_default():
    """The client asked for hands-off publishing; the shipped default reflects that."""
    shipped = Settings(_env_file=None, _env_prefix="__none__")  # type: ignore[call-arg]
    assert shipped.auto_publish_en is True
    assert shipped.auto_publish_ru is True
    # Slack stays optional: nothing breaks when it is not configured.
    assert shipped.slack_enabled is False


def test_article_card_mentions_automatic_publishing(session, settings):
    card = sb.article_card(
        make_article(session), admin_url="https://engine.example", auto_publish=True
    )
    rendered = json.dumps(card, ensure_ascii=False)
    assert "автоматически" in rendered
    assert sb.ACTION_REJECT in rendered


@pytest.mark.parametrize("action", [sb.ACTION_PUBLISH, sb.ACTION_REJECT, sb.ACTION_REGENERATE])
def test_every_button_has_an_action_id(session, settings, action):
    card = sb.article_card(
        make_article(session), admin_url="https://engine.example", auto_publish=True
    )
    assert action in json.dumps(card)
