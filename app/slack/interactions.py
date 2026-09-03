"""Slack request verification and button handling."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Article
from app.logging_setup import get_logger
from app.services.workflow import ArticleWorkflow
from app.slack import blocks as sb

log = get_logger("slack.interactions")

#: Slack rejects anything older than five minutes; so do we, to stop replay attacks.
MAX_REQUEST_AGE_SECONDS = 60 * 5


def verify_signature(
    *, signing_secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None
) -> bool:
    """Validate ``X-Slack-Signature`` (v0 scheme)."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs((now or time.time()) - sent_at) > MAX_REQUEST_AGE_SECONDS:
        return False

    basestring = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@dataclass(slots=True)
class InteractionResult:
    text: str
    ok: bool = True

    def as_response(self) -> dict[str, Any]:
        return {
            "response_type": "ephemeral",
            "replace_original": False,
            "blocks": sb.result_card(self.text, ok=self.ok),
        }


class InteractionHandler:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.workflow = ArticleWorkflow(session, self.settings)

    def handle(self, payload: dict[str, Any]) -> InteractionResult:
        actions = payload.get("actions") or []
        if not actions:
            return InteractionResult("Нечего делать: в запросе нет действия", ok=False)

        action = actions[0]
        action_id = str(action.get("action_id", ""))
        value = str(action.get("value", ""))
        user = (payload.get("user") or {}).get("username") or "slack"

        article = self.session.get(Article, int(value)) if value.isdigit() else None
        if article is None:
            return InteractionResult(f"Статья {value} не найдена", ok=False)

        log.info(
            "slack.action",
            action=action_id,
            article_id=article.id,
            user=user,
            market=article.market,
        )

        match action_id:
            case sb.ACTION_PUBLISH:
                result = self.workflow.publish_now(article, require_test=False)
                return InteractionResult(result.message, ok=result.ok)
            case sb.ACTION_PUBLISH_TEST:
                result = self.workflow.publish_test(article)
                return InteractionResult(result.message, ok=result.ok)
            case sb.ACTION_REJECT:
                result = self.workflow.reject(
                    article, reason=f"снято через Slack ({user})", by=user
                )
                return InteractionResult(
                    f"Статья снята с публикации: {article.title or article.primary_query}",
                    ok=result.ok,
                )
            case sb.ACTION_REGENERATE:
                outcome = self.workflow.regenerate(article)
                if outcome.article is None:
                    return InteractionResult(
                        f"Перегенерация не выполнена: {outcome.reason}", ok=False
                    )
                return InteractionResult(
                    f"Перегенерировано, новый черновик #{outcome.article.id} ({outcome.status})"
                )
        return InteractionResult(f"Неизвестное действие {action_id}", ok=False)


__all__ = [
    "MAX_REQUEST_AGE_SECONDS",
    "InteractionHandler",
    "InteractionResult",
    "verify_signature",
]
