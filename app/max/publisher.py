"""Best-effort Max fan-out after a successful Telegram RU production publish.

Forward-only: Max never backfills historical Telegram posts. When Max was
connected later than Telegram, it simply starts mirroring new RU production
publishes from that point on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.db.models import Article
from app.logging_setup import get_logger
from app.max.client import MaxBotClient, SentMaxMessage, build_max_client
from app.max.renderer import render_max_payload

log = get_logger("max.publisher")


@dataclass(slots=True)
class MaxPublishResult:
    sent: SentMaxMessage | None
    skipped: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.skipped or self.sent is not None)


class MaxPublisher:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: MaxBotClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def _ensure_client(self) -> MaxBotClient | None:
        if self._client is not None:
            return self._client
        self._client = build_max_client(self.settings)
        return self._client

    def publish_ru(self, article: Article) -> MaxPublishResult:
        """Publish one RU article to Max. Never raises for transport failures."""
        if article.market != "ru":
            return MaxPublishResult(sent=None, skipped=True)
        if not self.settings.max_ru_active:
            return MaxPublishResult(sent=None, skipped=True)

        client = self._ensure_client()
        if client is None:
            return MaxPublishResult(sent=None, skipped=True)

        try:
            payload = render_max_payload(article)
            sent = client.send_message(
                text=str(payload["text"]),
                attachments=payload.get("attachments"),
                format=payload.get("format") or "markdown",
            )
        except Exception as exc:  # noqa: BLE001 — secondary surface must not break Telegram
            log.error(
                "max.publish_failed",
                article_id=article.id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return MaxPublishResult(sent=None, skipped=False, error=str(exc))

        log.info(
            "max.published",
            article_id=article.id,
            chat_id=sent.chat_id,
            message_id=sent.message_id,
        )
        return MaxPublishResult(sent=sent, skipped=False)


def maybe_publish_ru_to_max(
    article: Article,
    *,
    settings: Settings | None = None,
) -> MaxPublishResult:
    """Convenience wrapper used by the Telegram publish paths."""
    publisher = MaxPublisher(settings=settings)
    try:
        return publisher.publish_ru(article)
    finally:
        publisher.close()


def max_smoke_details(settings: Settings | None = None) -> dict[str, Any]:
    """Return diagnostic info for ``wgt check-max`` (raises on hard misconfig)."""
    settings = settings or get_settings()
    if not settings.max_ru_active:
        return {"configured": False}
    client = MaxBotClient(settings)
    try:
        me = client.get_me()
        chat = client.get_chat()
        return {
            "configured": True,
            "bot": {
                "user_id": me.get("user_id"),
                "username": me.get("username"),
                "name": me.get("name") or me.get("first_name"),
            },
            "chat": {
                "chat_id": chat.get("chat_id"),
                "title": chat.get("title"),
                "type": chat.get("type"),
                "status": chat.get("status"),
            },
        }
    finally:
        client.close()


__all__ = [
    "MaxPublishResult",
    "MaxPublisher",
    "max_smoke_details",
    "maybe_publish_ru_to_max",
]
