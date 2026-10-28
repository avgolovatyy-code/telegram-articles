"""Best-effort Max fan-out after a successful Telegram RU production publish.

Forward-only: Max never backfills historical Telegram posts. When Max was
connected later than Telegram, it simply starts mirroring new RU production
publishes from that point on — **only** if ``MaxRussiaEditorialPolicy`` allows
the topic for residents of Russia (addendum v1.1 §6.1).

Format separation (same article, two surfaces):
- Telegram keeps block-based ``InputRichMessage`` via ``sendRichMessage``.
- Max adapts ``article.body`` (``adapt_for_max``) then renders Max HTML + buttons.
  It never reads or overwrites ``article.rendered_message``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Article, MaxPublication
from app.db.types import utcnow
from app.logging_setup import get_logger
from app.max.adapter import AdaptedMaxPost, adapt_for_max
from app.max.chat_id import CANONICAL_PUBLIC_SLUG, CANONICAL_PUBLIC_URL
from app.max.client import MaxBotClient, SentMaxMessage, build_max_client
from app.max.policy import MaxRussiaEditorialPolicy, MaxTopicEvaluation
from app.max.quota import max_quota_decision
from app.max.renderer import render_max_payload
from app.topics.geo import GeoResolver, TopicGeo

log = get_logger("max.publisher")


def max_idempotency_key(article_id: int, version: int, target: str = "production") -> str:
    return f"article:{article_id}:v{version}:max:{target}"


def _message_url_from_raw(raw: dict[str, Any], *, public_url: str) -> str | None:
    message: dict[str, Any] = {}
    raw_message = raw.get("message")
    if isinstance(raw_message, dict):
        message = dict(raw_message)
    stat: dict[str, Any] = {}
    raw_stat = message.get("stat")
    if isinstance(raw_stat, dict):
        stat = dict(raw_stat)
    for key in ("url", "link"):
        value = stat.get(key) or message.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return public_url or None


@dataclass(slots=True)
class MaxPublishResult:
    sent: SentMaxMessage | None
    skipped: bool
    error: str | None = None
    skip_reason: str | None = None
    evaluation: MaxTopicEvaluation | None = None
    publication: MaxPublication | None = None
    adapted: AdaptedMaxPost | None = None

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

    def _public_url(self) -> str:
        return self.settings.maxapp_channel_public_url or CANONICAL_PUBLIC_URL

    def _channel_ref(self) -> str:
        return CANONICAL_PUBLIC_SLUG

    def _resolve_geo(self, article: Article) -> TopicGeo:
        if self.session is not None:
            return GeoResolver(self.session, "ru").resolve(
                entity_type=article.entity_type,
                entity_external_id=article.entity_external_id,
                product_ids=[p.product_external_id for p in (article.products or [])],
            )
        return TopicGeo(
            country_id=None,
            city_id=None,
            attraction_id=None,
            is_russia=False,
        )

    def _existing(self, article: Article) -> MaxPublication | None:
        if self.session is None:
            return None
        key = max_idempotency_key(article.id, article.current_version)
        return self.session.scalar(
            select(MaxPublication).where(MaxPublication.idempotency_key == key)
        )

    def _record(
        self,
        article: Article,
        *,
        sent: SentMaxMessage | None,
        skipped: bool,
        skip_reason: str | None,
        evaluation: MaxTopicEvaluation | None,
        adapted: AdaptedMaxPost | None,
    ) -> MaxPublication | None:
        if self.session is None:
            return None
        key = max_idempotency_key(article.id, article.current_version)
        existing = self._existing(article)
        if existing is not None:
            return existing
        row = MaxPublication(
            article_id=article.id,
            idempotency_key=key,
            market="ru",
            target="production",
            chat_id=str(sent.chat_id) if sent else None,
            channel_ref=self._channel_ref(),
            message_id=sent.message_id if sent else None,
            message_url=(
                _message_url_from_raw(sent.raw, public_url=self._public_url()) if sent else None
            ),
            article_version=article.current_version,
            audience_country=self.settings.maxapp_audience_country or "RU",
            benefit=evaluation.decision.benefit if evaluation else None,
            domestic_or_outbound=evaluation.domestic_or_outbound if evaluation else None,
            skip_reason=skip_reason,
            skipped=skipped,
            adaptation=adapted.as_dict() if adapted else None,
            max_response=sent.raw if sent else None,
            published_at=utcnow(),
        )
        self.session.add(row)
        try:
            self.session.flush()
        except Exception as exc:
            # Never roll back Telegram because Max audit insert failed.
            log.error("max.persist_failed", article_id=article.id, error=str(exc))
            return None
        return row

    def publish_ru(self, article: Article) -> MaxPublishResult:
        """Publish one RU article to Max. Never raises for transport failures."""
        if article.market != "ru":
            return MaxPublishResult(sent=None, skipped=True, skip_reason="non_ru_market")
        if not self.settings.max_ru_active:
            return MaxPublishResult(sent=None, skipped=True, skip_reason="max_inactive")
        from app.editorial.eligibility import article_meets_editorial_spec

        if not article_meets_editorial_spec(article, self.settings):
            return MaxPublishResult(
                sent=None, skipped=True, skip_reason="pre_editorial_spec_cutoff"
            )

        existing = self._existing(article)
        if existing is not None and not existing.skipped and existing.message_id:
            log.info(
                "max.already_published",
                article_id=article.id,
                message_id=existing.message_id,
            )
            return MaxPublishResult(
                sent=None,
                skipped=True,
                skip_reason="already_published",
                publication=existing,
            )

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
            pub = self._record(
                article,
                sent=None,
                skipped=True,
                skip_reason=evaluation.skip_reason or "audience_gate",
                evaluation=evaluation,
                adapted=None,
            )
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
                publication=pub,
            )

        allowed, quota_reason = max_quota_decision(self.session, self.settings)
        if not allowed:
            pub = self._record(
                article,
                sent=None,
                skipped=True,
                skip_reason=quota_reason,
                evaluation=evaluation,
                adapted=None,
            )
            return MaxPublishResult(
                sent=None,
                skipped=True,
                skip_reason=quota_reason,
                evaluation=evaluation,
                publication=pub,
            )

        client = self._ensure_client()
        if client is None:
            return MaxPublishResult(
                sent=None, skipped=True, skip_reason="no_client", evaluation=evaluation
            )

        try:
            adapted = adapt_for_max(article)
            payload = render_max_payload(
                article,
                settings=self.settings,
                document=adapted.document,
                title=adapted.title,
            )
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
        pub = self._record(
            article,
            sent=sent,
            skipped=False,
            skip_reason=None,
            evaluation=evaluation,
            adapted=adapted,
        )
        log.info(
            "max.published",
            article_id=article.id,
            chat_id=sent.chat_id,
            message_id=sent.message_id,
            public_url=self._public_url(),
            benefit=evaluation.decision.benefit,
            domestic_or_outbound=evaluation.domestic_or_outbound,
            adapted_chars=adapted.char_estimate,
        )
        return MaxPublishResult(
            sent=sent,
            skipped=False,
            evaluation=evaluation,
            publication=pub,
            adapted=adapted,
        )


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
        link = chat.get("link") or chat.get("username") or ""
        return {
            "configured": True,
            "public_url": public_url,
            "audience_country": settings.maxapp_audience_country,
            "domestic_share_target": settings.maxapp_ru_domestic_share_target,
            "outbound_share_target": settings.maxapp_ru_outbound_share_target,
            "posts_per_week_max": settings.maxapp_posts_per_week_max,
            "posts_per_day_max": settings.maxapp_max_posts_per_day,
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
                "link": link,
                "is_public": chat.get("is_public"),
                "matches_canonical_slug": (
                    "channel_wegotrip" in str(link).casefold()
                    or str(link).endswith("channel_wegotrip")
                ),
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
    "max_idempotency_key",
    "max_smoke_details",
    "maybe_publish_ru_to_max",
]
