"""Europe/Moscow weekday policy for Dzen Slack delivery.

The Slack API must not be called for staff-facing Dzen messages on Saturday or
Sunday. Mention budget is one message per local workday, hard cap.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import Settings

DAY_CODES: dict[str, int] = {
    "MO": 0,
    "MON": 0,
    "TU": 1,
    "TUE": 1,
    "WE": 2,
    "WED": 2,
    "TH": 3,
    "THU": 3,
    "FR": 4,
    "FRI": 4,
    "SA": 5,
    "SAT": 5,
    "SU": 6,
    "SUN": 6,
}

FIXED_WEEKDAYS = "fixed_weekdays"
WEEKDAYS_IF_READY = "weekdays_if_ready"
EVERY_2_WORKDAYS = "every_2_workdays"
BATCH_MODES = (FIXED_WEEKDAYS, WEEKDAYS_IF_READY, EVERY_2_WORKDAYS)


def dzen_tz(settings: Settings) -> ZoneInfo:
    name = (settings.dzen_slack_timezone or settings.publish_timezone or "Europe/Moscow").strip()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def local_now(settings: Settings, now: dt.datetime | None = None) -> dt.datetime:
    clock = now or dt.datetime.now(dt.UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=dt.UTC)
    return clock.astimezone(dzen_tz(settings))


def parse_weekdays(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset({1, 3})  # Tuesday, Thursday
    days: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        token = part.strip().upper()
        if not token:
            continue
        if token in DAY_CODES:
            days.add(DAY_CODES[token])
            continue
        if token.isdigit() and 0 <= int(token) <= 6:
            days.add(int(token))
    return frozenset(days) or frozenset({1, 3})


def is_weekend(local: dt.datetime) -> bool:
    return local.weekday() >= 5


def workdays_between(start: dt.date, end: dt.date) -> int:
    """Inclusive count of Mon–Fri dates from start+1 through end."""
    if end <= start:
        return 0
    count = 0
    cursor = start + dt.timedelta(days=1)
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += dt.timedelta(days=1)
    return count


def is_delivery_day(
    settings: Settings,
    local: dt.datetime,
    *,
    last_send_date: dt.date | None = None,
    batch_mode: str | None = None,
) -> bool:
    if settings.dzen_slack_weekdays_only and is_weekend(local):
        return False
    mode = (batch_mode or settings.dzen_slack_batch_mode or FIXED_WEEKDAYS).strip()
    if mode == WEEKDAYS_IF_READY:
        return local.weekday() < 5
    if mode == EVERY_2_WORKDAYS:
        if local.weekday() >= 5:
            return False
        if last_send_date is None:
            return True
        return workdays_between(last_send_date, local.date()) >= 2
    return local.weekday() in parse_weekdays(settings.dzen_slack_delivery_days)


def at_or_after_notify_hour(settings: Settings, local: dt.datetime) -> bool:
    hour = int(settings.dzen_slack_notify_hour)
    minute = int(settings.dzen_slack_notify_minute)
    return (local.hour, local.minute) >= (hour, minute)


def may_send_staff_digest(
    settings: Settings,
    *,
    now: dt.datetime | None = None,
    last_send_date: dt.date | None = None,
    pings_today: int = 0,
    force_hour: bool = False,
    batch_mode: str | None = None,
) -> tuple[bool, str]:
    """Return whether a staff-facing Dzen Slack message may be sent."""
    if not settings.dzen_enabled:
        return False, "dzen_disabled"
    if settings.dzen_native_autopublish_enabled:
        return False, "native_autopublish_forbidden"
    local = local_now(settings, now)
    if settings.dzen_slack_weekdays_only and is_weekend(local):
        return False, "weekend"
    if pings_today >= max(1, int(settings.dzen_slack_max_ping_per_workday)):
        return False, "mention_budget_exhausted"
    if not is_delivery_day(settings, local, last_send_date=last_send_date, batch_mode=batch_mode):
        return False, "not_delivery_day"
    if not force_hour and not at_or_after_notify_hour(settings, local):
        return False, "before_notify_hour"
    channel = resolved_slack_channel(settings)
    if not channel:
        return False, "channel_unresolved"
    mention = (settings.dzen_slack_mention_user_id or "").strip()
    if not mention.startswith("U"):
        return False, "mention_user_unresolved"
    return True, "ok"


def resolved_slack_channel(settings: Settings) -> str | None:
    """Only a confirmed channel id (C…/G…) is eligible. Never invent a name."""
    for candidate in (settings.dzen_slack_channel_id, settings.slack_channel):
        value = (candidate or "").strip()
        if len(value) >= 9 and value[0] in {"C", "G", "D"} and value[1:].isalnum():
            return value
    return None


def mention_markup(settings: Settings) -> str:
    user_id = (settings.dzen_slack_mention_user_id or "").strip()
    return f"<@{user_id}>" if user_id.startswith("U") else ""


__all__ = [
    "BATCH_MODES",
    "EVERY_2_WORKDAYS",
    "FIXED_WEEKDAYS",
    "WEEKDAYS_IF_READY",
    "at_or_after_notify_hour",
    "dzen_tz",
    "is_delivery_day",
    "is_weekend",
    "local_now",
    "may_send_staff_digest",
    "mention_markup",
    "parse_weekdays",
    "resolved_slack_channel",
    "workdays_between",
]
