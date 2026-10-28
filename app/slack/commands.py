"""The `/wegotrip` slash command."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.budget import BudgetManager
from app.config import MARKETS, Settings, get_settings
from app.db.enums import ArticleStatus
from app.db.models import Article
from app.slack import blocks as sb
from app.topics.coverage import assess_coverage

HELP = (
    "*Команды:*\n"
    "`/wegotrip status` — бюджет, сгенерировано и опубликовано сегодня\n"
    "`/wegotrip coverage` — сколько материала в каталоге ещё не описано\n"
    "`/wegotrip pending` — статьи, ожидающие публикации\n"
    "`/wegotrip help` — эта справка"
)


class CommandHandler:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def handle(self, text: str) -> dict[str, Any]:
        command = (text or "").strip().split(" ", 1)[0].lower() or "status"
        match command:
            case "status":
                return self._ephemeral(self._status())
            case "coverage":
                return self._ephemeral(self._coverage())
            case "pending":
                return self._ephemeral(self._pending())
            case "help":
                return self._ephemeral(HELP)
        return self._ephemeral(f"Неизвестная команда `{command}`.\n\n{HELP}")

    # ---------------------------------------------------------------- sections
    def _status(self) -> str:
        snapshot = BudgetManager(self.session, self.settings).snapshot()
        lines = [
            f"*Бюджет:* потрачено ${snapshot.spent_usd:.2f} из ${snapshot.budget_usd:.2f}, "
            f"остаток ${snapshot.remaining_usd:.2f}",
            f"*Сгенерировано сегодня:* EN {snapshot.generated.get('en', 0)} · "
            f"RU {snapshot.generated.get('ru', 0)}",
            f"*Средняя стоимость статьи:* ${snapshot.average_article_cost_usd:.4f}",
        ]
        for market in MARKETS:
            auto = "включена" if self.settings.auto_publish(market) else "выключена"
            lines.append(f"*Автопубликация {market.upper()}:* {auto}")
        return "\n".join(lines)

    def _coverage(self) -> str:
        lines = []
        for market in MARKETS:
            report = assess_coverage(self.session, market, self.settings)
            flag = sb.MARKET_FLAG.get(market, market)
            lines.append(
                f"{flag} осталось тем: *{report.usable_candidates}*, написано "
                f"{report.used_topics}, товаров {report.available_products}"
            )
            lines.append(f"     _{report.reason}_")
        return "\n".join(lines)

    def _pending(self) -> str:
        rows = list(
            self.session.scalars(
                select(Article)
                .where(
                    Article.status.in_(
                        [
                            ArticleStatus.NEEDS_REVIEW,
                            ArticleStatus.APPROVED,
                            ArticleStatus.SCHEDULED,
                        ]
                    )
                )
                .order_by(Article.scheduled_for.is_(None), Article.scheduled_for)
                .limit(15)
            ).all()
        )
        if not rows:
            return "Очередь пуста — всё опубликовано."
        lines = ["*Ожидают публикации:*"]
        for article in rows:
            when = (
                article.scheduled_for.strftime("%d.%m %H:%M UTC")
                if article.scheduled_for
                else "время не назначено"
            )
            flag = sb.MARKET_FLAG.get(article.market, article.market)
            title = article.title or article.primary_query
            lines.append(f"{flag} #{article.id} *{title}* — {when}")
        return "\n".join(lines)

    @staticmethod
    def _ephemeral(markdown: str) -> dict[str, Any]:
        return {
            "response_type": "ephemeral",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": markdown}}],
        }


__all__ = ["HELP", "CommandHandler"]
