"""Editorial Engine v2.2 publication cadence (§3).

When ``editorial_v2_enabled`` is on, the legacy scheduler still respects weekly caps,
daily post limits, and minimum spacing between publishes.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings
from app.db.enums import ArticleStatus
from app.db.models import Article
from app.db.types import utcnow

# Rolling window for «posts per week» (publish timezone, calendar days).
ROLLING_WEEK_DAYS = 7


def editorial_v2_cadence_active(settings: Settings) -> bool:
    return bool(settings.editorial_v2_enabled)


def effective_min_post_interval_minutes(settings: Settings) -> int:
    """Spec §3: ≥6h between publishes when v2 cadence is active."""
    if editorial_v2_cadence_active(settings):
        return max(settings.min_post_interval_minutes, 360)
    return settings.min_post_interval_minutes


def posts_per_week_hard_cap(settings: Settings, market: Market) -> int:
    if market == "ru":
        return settings.ru_posts_per_week_hard_cap
    return settings.en_posts_per_week_hard_cap


def posts_per_week_target_max(settings: Settings, market: Market) -> int:
    if market == "ru":
        return settings.ru_posts_per_week_max
    return settings.en_posts_per_week_max


def _rolling_week_bounds(
    moment: dt.datetime, settings: Settings
) -> tuple[dt.datetime, dt.datetime]:
    """UTC bounds for the rolling week ending at ``moment`` (inclusive end)."""
    end = moment.astimezone(dt.UTC)
    start = end - dt.timedelta(days=ROLLING_WEEK_DAYS)
    return start, end


def _commit_timestamp(article: Article) -> dt.datetime | None:
    if article.published_at is not None:
        return article.published_at
    if article.scheduled_for is not None:
        return article.scheduled_for
    return None


def production_posts_in_rolling_week(
    session: Session, market: Market, settings: Settings, *, now: dt.datetime | None = None
) -> int:
    """Count published and scheduled production posts in the rolling 7-day window."""
    now = now or utcnow()
    start, end = _rolling_week_bounds(now, settings)
    statuses = (
        ArticleStatus.PUBLISHED,
        ArticleStatus.SCHEDULED,
    )
    rows = session.scalars(
        select(Article).where(
            Article.market == market,
            Article.status.in_(statuses),
        )
    ).all()
    count = 0
    for article in rows:
        ts = _commit_timestamp(article)
        if ts is None:
            continue
        if start <= ts.astimezone(dt.UTC) <= end:
            count += 1
    return count


def production_posts_today(
    session: Session, market: Market, settings: Settings, *, now: dt.datetime | None = None
) -> int:
    """Published or scheduled production posts on the local publish day."""
    now = now or utcnow()
    local = now.astimezone(settings.publish_tz)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + dt.timedelta(days=1)
    start = start_local.astimezone(dt.UTC)
    end = end_local.astimezone(dt.UTC)
    rows = session.scalars(
        select(Article).where(
            Article.market == market,
            Article.status.in_((ArticleStatus.PUBLISHED, ArticleStatus.SCHEDULED)),
        )
    ).all()
    count = 0
    for article in rows:
        ts = _commit_timestamp(article)
        if ts is None:
            continue
        if start <= ts.astimezone(dt.UTC) < end:
            count += 1
    return count


def remaining_weekly_publish_slots(
    session: Session, market: Market, settings: Settings, *, use_hard_cap: bool = True
) -> int:
    if not editorial_v2_cadence_active(settings):
        return 10_000
    used = production_posts_in_rolling_week(session, market, settings)
    cap = (
        posts_per_week_hard_cap(settings, market)
        if use_hard_cap
        else posts_per_week_target_max(settings, market)
    )
    return max(0, cap - used)


def remaining_daily_publish_slots(
    session: Session, market: Market, settings: Settings, *, planned_today: int
) -> int:
    """How many more posts may be scheduled today under v2 daily cap."""
    if not editorial_v2_cadence_active(settings):
        return 10_000
    return max(0, settings.max_posts_per_day - planned_today)


__all__ = [
    "editorial_v2_cadence_active",
    "effective_min_post_interval_minutes",
    "posts_per_week_hard_cap",
    "posts_per_week_target_max",
    "production_posts_in_rolling_week",
    "production_posts_today",
    "remaining_daily_publish_slots",
    "remaining_weekly_publish_slots",
]
