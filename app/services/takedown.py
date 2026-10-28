"""Remove Telegram posts for an article and mark it archived."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.enums import ArticleStatus
from app.db.models import Article, TelegramPublication
from app.editorial.eligibility import editorial_spec_cutoff_utc
from app.errors import EngineError
from app.logging_setup import get_logger
from app.telegram.api import build_telegram_client

log = get_logger("services.takedown")


@dataclass(slots=True)
class TakedownResult:
    ok: bool
    message: str
    deleted: int = 0
    errors: list[str] | None = None


class ArticleTakedown:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def takedown(self, article: Article, *, reason: str = "editorial takedown") -> TakedownResult:
        client = build_telegram_client(self.settings)
        deleted = 0
        errors: list[str] = []
        try:
            for publication in list(article.publications):
                if publication.message_id is None or not publication.chat_id:
                    continue
                try:
                    client.delete_message(publication.chat_id, publication.message_id)
                    deleted += 1
                    log.info(
                        "takedown.deleted",
                        article_id=article.id,
                        target=publication.target,
                        message_id=publication.message_id,
                    )
                except EngineError as exc:
                    errors.append(f"{publication.target}:{publication.message_id}: {exc}")
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        article.status = ArticleStatus.ARCHIVED
        article.status_reason = reason
        self.session.flush()

        ok = deleted > 0 or not any(p.message_id for p in article.publications)
        msg = f"archived article {article.id}; deleted {deleted} Telegram message(s)"
        if errors:
            msg += f"; errors: {'; '.join(errors)}"
        return TakedownResult(ok=ok, message=msg, deleted=deleted, errors=errors or None)


def takedown_legacy_published_since(
    session: Session,
    *,
    since: dt.datetime,
    settings: Settings | None = None,
) -> list[TakedownResult]:
    """Take down production posts for pre-cutoff articles published on/after ``since``."""
    settings = settings or get_settings()
    cutoff = editorial_spec_cutoff_utc(settings)
    if cutoff is None:
        return []

    service = ArticleTakedown(session, settings)
    results: list[TakedownResult] = []
    rows = session.scalars(
        select(Article)
        .join(TelegramPublication)
        .where(
            TelegramPublication.target == "production",
            TelegramPublication.published_at >= since,
            Article.created_at < cutoff,
        )
        .distinct()
    ).all()
    for article in rows:
        results.append(service.takedown(article, reason="legacy post removed per editorial spec"))
    return results


__all__ = ["ArticleTakedown", "TakedownResult", "takedown_legacy_published_since"]
