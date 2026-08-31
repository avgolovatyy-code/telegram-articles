"""Slack notifications.

The engine publishes on its own; Slack is where you watch it and step in if you want to.
Every notification failure is swallowed — a broken Slack integration must never stop a
publication.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.budget import BudgetManager
from app.config import MARKETS, Settings, get_settings
from app.db.enums import ArticleStatus
from app.db.models import Article
from app.db.types import utcnow
from app.logging_setup import get_logger
from app.slack import blocks as sb
from app.slack.client import build_slack_client
from app.topics.coverage import assess_coverage

log = get_logger("slack.notifications")


class SlackNotifier:
    def __init__(
        self, session: Session, settings: Settings | None = None, client: Any = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.client = client or build_slack_client(self.settings)

    @property
    def enabled(self) -> bool:
        return self.settings.slack_active

    def _send(self, blocks: list[dict[str, Any]], text: str) -> None:
        if not self.enabled:
            return
        try:
            self.client.post_message(blocks=blocks, text=text)
        except Exception as exc:
            log.warning("slack.notify_failed", error=f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ events
    def article_drafted(self, article: Article) -> None:
        if not self.settings.slack_notify_on_draft:
            return
        auto = self.settings.auto_publish(article.market)  # type: ignore[arg-type]
        self._send(
            sb.article_card(article, admin_url=self.settings.admin_base_url, auto_publish=auto),
            f"Новая статья: {article.title or article.primary_query}",
        )

    def article_published(self, article: Article, *, message_url: str | None, channel: str) -> None:
        if not self.settings.slack_notify_on_publish:
            return
        self._send(
            sb.published_card(article, message_url=message_url, channel=channel),
            f"Опубликовано: {article.title or article.primary_query}",
        )

    def alert(self, title: str, detail: str) -> None:
        self._send(sb.alert_card(title, detail), title)

    def daily_digest(self) -> None:
        budget = BudgetManager(self.session, self.settings).snapshot()
        coverage: dict[str, Any] = {
            market: assess_coverage(self.session, market, self.settings) for market in MARKETS
        }
        start = dt.datetime.combine(utcnow().date(), dt.time.min, tzinfo=dt.UTC)
        published: dict[str, int] = {
            market: int(
                self.session.scalar(
                    select(func.count(Article.id)).where(
                        Article.market == market,
                        Article.status == ArticleStatus.PUBLISHED,
                        Article.published_at >= start,
                    )
                )
                or 0
            )
            for market in MARKETS
        }
        self._send(
            sb.digest_card(
                budget=budget,
                coverage=coverage,
                published_today=published,
                admin_url=self.settings.admin_base_url,
            ),
            "Сводка за день",
        )


__all__ = ["SlackNotifier"]
