"""Max RU publish quotas (addendum §5): soft weekly / hard daily caps."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import MaxPublication


def _moscow_now(tz_name: str = "Europe/Moscow") -> dt.datetime:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return dt.datetime.now(dt.UTC).astimezone(tz)


def moscow_day_bounds(tz_name: str = "Europe/Moscow") -> tuple[dt.datetime, dt.datetime]:
    local = _moscow_now(tz_name)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + dt.timedelta(days=1)
    return start_local.astimezone(dt.UTC), end_local.astimezone(dt.UTC)


def moscow_week_bounds(tz_name: str = "Europe/Moscow") -> tuple[dt.datetime, dt.datetime]:
    """ISO week Mon–Sun in the editorial timezone."""
    local = _moscow_now(tz_name)
    start_local = (local - dt.timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_local = start_local + dt.timedelta(days=7)
    return start_local.astimezone(dt.UTC), end_local.astimezone(dt.UTC)


def count_max_publishes(
    session: Session,
    *,
    since: dt.datetime,
    until: dt.datetime,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(MaxPublication)
            .where(
                MaxPublication.published_at >= since,
                MaxPublication.published_at < until,
                MaxPublication.skipped.is_(False),
            )
        )
        or 0
    )


def max_quota_decision(
    session: Session | None,
    settings: Settings,
) -> tuple[bool, str | None]:
    """Return ``(allowed, skip_reason)`` for another Max production post."""
    if session is None:
        return True, None
    tz = settings.maxapp_editorial_timezone or settings.publish_timezone
    day_start, day_end = moscow_day_bounds(tz)
    today = count_max_publishes(session, since=day_start, until=day_end)
    if today >= max(1, settings.maxapp_max_posts_per_day):
        return False, "max_daily_quota"

    week_start, week_end = moscow_week_bounds(tz)
    week = count_max_publishes(session, since=week_start, until=week_end)
    if week >= max(1, settings.maxapp_posts_per_week_max):
        return False, "max_weekly_quota"
    return True, None


__all__ = [
    "count_max_publishes",
    "max_quota_decision",
    "moscow_day_bounds",
    "moscow_week_bounds",
]
