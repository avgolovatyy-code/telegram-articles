from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.dzen.policy import is_delivery_day, may_send_staff_digest, resolved_slack_channel

MSK = ZoneInfo("Europe/Moscow")


def _at(day: int, hour: int, minute: int = 0) -> dt.datetime:
    # November 2026: 16=Mon ... 22=Sun
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=MSK)


def test_resolved_channel_requires_c_id(settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", None)
    monkeypatch.setattr(settings, "slack_channel", "[REDACTED]")
    assert resolved_slack_channel(settings) is None
    monkeypatch.setattr(settings, "slack_channel", "C0BTME6R546")
    assert resolved_slack_channel(settings) == "C0BTME6R546"
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C1234567890")
    assert resolved_slack_channel(settings) == "C1234567890"


def test_monday_off_by_default(settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    monkeypatch.setattr(settings, "dzen_slack_delivery_days", "TU,TH")
    monkeypatch.setattr(settings, "dzen_slack_batch_mode", "fixed_weekdays")
    ok, reason = may_send_staff_digest(settings, now=_at(16, 11), force_hour=True)
    assert ok is False
    assert reason == "not_delivery_day"


def test_tuesday_allows_one_digest(settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    ok, reason = may_send_staff_digest(settings, now=_at(17, 11), force_hour=True)
    assert ok is True
    assert reason == "ok"


def test_weekend_blocks_even_if_hour_matches(settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    for day in (21, 22):
        ok, reason = may_send_staff_digest(settings, now=_at(day, 11), force_hour=True)
        assert ok is False
        assert reason == "weekend"


def test_friday_2359_and_weekdays_if_ready(settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    monkeypatch.setattr(settings, "dzen_slack_batch_mode", "weekdays_if_ready")
    ok, _ = may_send_staff_digest(settings, now=_at(20, 23, 59), force_hour=True)
    assert ok is True
    ok, reason = may_send_staff_digest(settings, now=_at(21, 11), force_hour=True)
    assert ok is False
    assert reason == "weekend"


def test_mention_budget(settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    ok, reason = may_send_staff_digest(settings, now=_at(17, 11), pings_today=1, force_hour=True)
    assert ok is False
    assert reason == "mention_budget_exhausted"


def test_every_two_workdays(settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    monkeypatch.setattr(settings, "dzen_slack_batch_mode", "every_2_workdays")
    last = dt.date(2026, 11, 17)  # Tuesday
    local = _at(18, 11)  # Wednesday = 1 workday later
    assert (
        is_delivery_day(settings, local, last_send_date=last, batch_mode="every_2_workdays")
        is False
    )
    thursday = _at(19, 11)
    assert (
        is_delivery_day(settings, thursday, last_send_date=last, batch_mode="every_2_workdays")
        is True
    )
