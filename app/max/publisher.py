"""Best-effort Max fan-out after a successful Telegram RU production publish.

Forward-only: Max never backfills historical Telegram posts. When Max was
connected later than Telegram, it simply starts mirroring new RU production
publishes from that point on — **only** if ``MaxRussiaEditorialPolicy`` allows
the topic for residents of Russia (addendum v1.1 §6.1).

Format separation (same article, two surfaces):
- Telegram keeps block-based ``InputRichMessage`` via ``sendRichMessage``.
- Max re-renders ``article.body`` into Max markdown/html + buttons.
  It never reads or overwrites ``article.rendered_message``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Article
from app.logging_setup import get_logger
from app.max.chat_id import CANONICAL_PUBLIC_URL
from app.max.client import MaxBotClient, SentMaxMessage, build_max_client
from app.max.policy import MaxRussiaEditorialPolicy, MaxTopicEvaluation
from app.max.renderer import render_max_payload
from app.topics.geo import GeoResolver, TopicGeo

log = get_logger("max.publisher")


@dataclass(slots=True)
class MaxPublishResult:
    sent: SentMaxMessage | None
    skipped: bool
    error: str | None = None
    skip_reason: str | None = None
    evaluation: MaxTopicEvaluation | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.skipped or self.sent is not None)


class MaxPublisher:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: MaxBotClient | None = None,
        session: Session | None = None,
        policy: MaxRussiaEditorialPolicy | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self.session = session
        self.policy = policy or MaxRussiaEditorialPolicy(
            domestic_share_target=self.settings.maxapp_ru_domestic_share_target,
            outbound_share_target=self.settings.maxapp_ru_outbound_share_target,
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def _ensure_client(self) -> MaxBotClient | None:
        if self._client is not None:
            return self._client
        self._client = build_max_client(self.settings)
        return self._client

    def _resolve_geo(self, article: Article) -> TopicGeo:
        if self.session is not None:
            return GeoResolver(self.session, "ru").resolve(
                entity_type=article.entity_type,
                entity_external_id=article.entity_external_id,
                product_ids=[p.product_external_id for p in (article.products or [])],
            )
        # Without a session: treat unknown foreign vs domestic conservatively —
        # still allow publish (outbound-from-RU default) rather than drop silently.
        return TopicGeo(
            country_id=None,
            city_id=None,
            attraction_id=None,
            is_russia=False,
        )

    def publish_ru(self, article: Article) -> MaxPublishResult:
        """Publish one RU article to Max. Never raises for transport failures."""
        if article.market != "ru":
            return MaxPublishResult(sent=None, skipped=True, skip_reason="non_ru_market")
        if not self.settings.max_ru_active:
            return MaxPublishResult(sent=None, skipped=True, skip_reason="max_inactive")

        geo = self._resolve_geo(article)
        evaluation = self.policy.evaluate(
            geo=geo,
            intent=article.intent,
            topic_id=str(article.id),
            entity_name=article.entity_name,
            city_name=article.entity_name if article.entity_type == "city" else None,
            product_available_on_ru_store=True,
        )
        if not evaluation.should_publish:
            log.info(
                "max.skipped_audience",
                article_id=article.id,
                reason=evaluation.skip_reason,
                relevance=evaluation.decision.relevance_for_russia,
                benefit=evaluation.decision.benefit,
            )
            return MaxPublishResult(
                sent=None,
                skipped=True,
                skip_reason=evaluation.skip_reason or "audience_gate",
                evaluation=evaluation,
            )

        client = self._ensure_client()
        if client is None:
            return MaxPublishResult(
                sent=None, skipped=True, skip_reason="no_client", evaluation=evaluation
            )

        try:
            payload = render_max_payload(article, settings=self.settings)
            sent = client.send_message(
                text=str(payload["text"]),
                attachments=payload.get("attachments"),
                format=payload.get("format") or "markdown",
            )
        except Exception as exc:
            log.error(
                "max.publish_failed",
                article_id=article.id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return MaxPublishResult(sent=None, skipped=False, error=str(exc), evaluation=evaluation)

        self.policy.observe_publish(evaluation)
        log.info(
            "max.published",
            article_id=article.id,
            chat_id=sent.chat_id,
            message_id=sent.message_id,
            public_url=self.settings.maxapp_channel_public_url or CANONICAL_PUBLIC_URL,
            benefit=evaluation.decision.benefit,
            domestic_or_outbound=evaluation.domestic_or_outbound,
        )
        return MaxPublishResult(sent=sent, skipped=False, evaluation=evaluation)


def maybe_publish_ru_to_max(
    article: Article,
    *,
    settings: Settings | None = None,
    session: Session | None = None,
) -> MaxPublishResult:
    """Convenience wrapper used by the Telegram publish paths."""
    publisher = MaxPublisher(settings=settings, session=session)
    try:
        return publisher.publish_ru(article)
    finally:
        publisher.close()


def max_smoke_details(settings: Settings | None = None) -> dict[str, Any]:
    """Return diagnostic info for ``wgt check-max`` (raises on hard misconfig)."""
    settings = settings or get_settings()
    public_url = settings.maxapp_channel_public_url or CANONICAL_PUBLIC_URL
    if not settings.max_ru_active:
        return {
            "configured": False,
            "public_url": public_url,
            "audience_country": settings.maxapp_audience_country,
        }
    client = MaxBotClient(settings)
    try:
        me = client.get_me()
        chat = client.get_chat()
        return {
            "configured": True,
            "public_url": public_url,
            "audience_country": settings.maxapp_audience_country,
            "domestic_share_target": settings.maxapp_ru_domestic_share_target,
            "outbound_share_target": settings.maxapp_ru_outbound_share_target,
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
                "link": chat.get("link") or chat.get("username"),
            },
            "note": (
                "Public URL rename must not change numeric MAX_RU_CHANNEL_ID; "
                "legacy max.ru/id* aliases are migration-only."
            ),
        }
    finally:
        client.close()


__all__ = [
    "MaxPublishResult",
    "MaxPublisher",
    "max_smoke_details",
    "maybe_publish_ru_to_max",
]
