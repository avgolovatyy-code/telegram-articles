"""Which stored articles may still be published under the current editorial spec."""

from __future__ import annotations

import datetime as dt

from app.config import Settings
from app.db.enums import ArticleStatus, PublicationTarget
from app.db.models import Article

_BLOCKED_STATUSES = frozenset(
    {
        ArticleStatus.VALIDATION_FAILED,
        ArticleStatus.FAILED,
        ArticleStatus.REJECTED,
        ArticleStatus.ARCHIVED,
        ArticleStatus.GENERATING,
        ArticleStatus.RESEARCHING,
    }
)


def editorial_spec_cutoff_utc(settings: Settings) -> dt.datetime | None:
    """Inclusive start of ``editorial_spec_cutoff_date`` in the publish timezone."""
    day = settings.editorial_spec_cutoff_date
    if day is None:
        return None
    local = dt.datetime.combine(day, dt.time.min, tzinfo=settings.publish_tz)
    return local.astimezone(dt.UTC)


def article_meets_editorial_spec(article: Article, settings: Settings) -> bool:
    cutoff = editorial_spec_cutoff_utc(settings)
    if cutoff is None:
        return True
    created = article.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=dt.UTC)
    return created >= cutoff


def publication_allowed(
    article: Article,
    settings: Settings,
    target: PublicationTarget | str,
) -> tuple[bool, str]:
    """Gate Telegram/Max publish paths (test + production)."""
    if str(target) != PublicationTarget.TEST and article.status in _BLOCKED_STATUSES:
        return False, f"cannot publish an article in status {article.status}"
    if article.status in _BLOCKED_STATUSES and str(target) == PublicationTarget.TEST:
        return False, f"cannot publish an article in status {article.status}"
    if not article_meets_editorial_spec(article, settings):
        return (
            False,
            "article predates EDITORIAL_SPEC_CUTOFF_DATE; regenerate or archive it",
        )
    return True, ""


__all__ = [
    "article_meets_editorial_spec",
    "editorial_spec_cutoff_utc",
    "publication_allowed",
]
