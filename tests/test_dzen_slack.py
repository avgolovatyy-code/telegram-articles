from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.dzen.slack_digest import send_dzen_digest
from app.scheduler import jobs
from app.slack.client import NullSlackClient
from tests.test_dzen_pipeline import ready_article

MSK = ZoneInfo("Europe/Moscow")


class RecordingSlack(NullSlackClient):
    def post_message(self, *, blocks, text, channel=None):
        if not hasattr(self, "payloads"):
            self.payloads = []
        self.payloads.append({"blocks": blocks, "text": text, "channel": channel})
        return super().post_message(blocks=blocks, text=text, channel=channel)


def _now(day: int, hour: int = 11) -> dt.datetime:
    return dt.datetime(2026, 11, day, hour, 0, tzinfo=MSK)


def test_tuesday_digest_one_mention_two_kits(synced_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    a1, _ = ready_article(synced_session, settings)
    a2, _ = ready_article(synced_session, settings)
    assert a1.public_id != a2.public_id
    client = RecordingSlack(settings)
    report = send_dzen_digest(
        synced_session, settings=settings, client=client, now=_now(17), force_hour=True
    )
    assert report.sent is True
    assert report.item_count == 2
    assert report.mentioned is True
    text = client.sent[0][1]
    assert text.count("<@U03AE1ATKDJ>") == 1
    assert "@U03AE1ATKDJ" not in text.replace("<@U03AE1ATKDJ>", "")
    assert "/dzen/k/" in text
    assert "Открыть готовую статью" in text or "dzen/k" in text
    assert "не страница Дзена" in text
    assert "не для поиска" in text

    again = send_dzen_digest(
        synced_session, settings=settings, client=client, now=_now(17), force_hour=True
    )
    assert again.sent is False
    assert again.reason == "already_sent_today"
    assert len(client.sent) == 1


def test_thursday_does_not_resend_old_items(synced_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    ready_article(synced_session, settings)
    client = RecordingSlack(settings)
    first = send_dzen_digest(
        synced_session, settings=settings, client=client, now=_now(17), force_hour=True
    )
    assert first.sent is True
    second = send_dzen_digest(
        synced_session, settings=settings, client=client, now=_now(19), force_hour=True
    )
    assert second.sent is False
    assert second.reason == "empty_queue"


def test_weekend_never_calls_slack(synced_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    ready_article(synced_session, settings)
    client = RecordingSlack(settings)
    for day in (21, 22):
        report = send_dzen_digest(
            synced_session, settings=settings, client=client, now=_now(day), force_hour=True
        )
        assert report.sent is False
        assert report.reason == "weekend"
    assert client.sent == []


def test_weekend_drafts_wait_for_monday_if_ready_mode(synced_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    monkeypatch.setattr(settings, "dzen_slack_batch_mode", "weekdays_if_ready")
    ready_article(synced_session, settings)
    client = RecordingSlack(settings)
    sat = send_dzen_digest(
        synced_session, settings=settings, client=client, now=_now(21), force_hour=True
    )
    assert sat.sent is False
    monday = send_dzen_digest(
        synced_session, settings=settings, client=client, now=_now(23), force_hour=True
    )
    assert monday.sent is True
    assert monday.item_count >= 1


def test_job_wrapper_skips_unresolved_channel(synced_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", None)
    monkeypatch.setattr(settings, "slack_channel", "")
    report = jobs.send_dzen_digest(synced_session, settings=settings, now=_now(17), force_hour=True)
    assert report.details["sent"] is False
    assert report.details["reason"] == "channel_unresolved"
