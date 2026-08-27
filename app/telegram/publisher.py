"""Idempotent Telegram publishing.

The idempotency key is ``article:<id>:v<version>:<target>``. It is unique on both
``publication_queue`` and ``telegram_publications``, so a retry, a worker restart or a
network timeout can never produce a second post: the publisher checks for an existing
publication first and claims the queue row with a lock before contacting Telegram.

A timeout is treated as *unknown*, not as failure: the row stays claimed and a
reconciliation pass decides, so the engine never re-posts a message that may have
already gone out.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Market, Settings, get_settings
from app.db.enums import ArticleStatus, PublicationStatus, PublicationTarget
from app.db.models import Article, PublicationQueueItem, TelegramPublication
from app.db.types import utcnow
from app.errors import (
    ConfigurationError,
    DuplicatePublication,
    TelegramError,
    TelegramRateLimited,
    TelegramValidationError,
)
from app.logging_setup import get_logger, new_job_id
from app.telegram.api import SentMessage
from app.telegram.blocks import validate_rich_message

log = get_logger("telegram.publisher")

#: A claimed queue row older than this is considered abandoned by a dead worker.
CLAIM_TTL = dt.timedelta(minutes=15)

MAX_PUBLISH_ATTEMPTS = 5


class TelegramClientProtocol(Protocol):
    def send_rich_message(
        self,
        chat_id: str,
        rich_message: dict[str, Any],
        *,
        disable_notification: bool = ...,
        protect_content: bool = ...,
    ) -> SentMessage: ...

    def edit_rich_message(
        self, chat_id: str, message_id: int, rich_message: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass(slots=True)
class PublicationResult:
    publication: TelegramPublication
    created: bool
    reused: bool = False


def idempotency_key(article_id: int, version: int, target: str) -> str:
    return f"article:{article_id}:v{version}:{target}"


class TelegramPublisher:
    def __init__(
        self,
        session: Session,
        client: TelegramClientProtocol,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.settings = settings or get_settings()

    # ------------------------------------------------------------- channels
    def channel_for(self, market: Market, target: PublicationTarget | str) -> str:
        if str(target) == PublicationTarget.TEST:
            channel = self.settings.telegram_test_channel
            if not channel:
                raise ConfigurationError(
                    "TELEGRAM_TEST_CHANNEL is not set; test publication is mandatory "
                    "before production"
                )
            return channel
        return self.settings.telegram_channel(market)

    # -------------------------------------------------------------- queueing
    def enqueue(
        self,
        article: Article,
        *,
        target: PublicationTarget | str = PublicationTarget.PRODUCTION,
        scheduled_for: dt.datetime | None = None,
    ) -> PublicationQueueItem:
        market: Market = article.market  # type: ignore[assignment]
        key = idempotency_key(article.id, article.current_version, str(target))
        existing = self.session.scalar(
            select(PublicationQueueItem).where(PublicationQueueItem.idempotency_key == key)
        )
        if existing is not None:
            if scheduled_for is not None and existing.status == PublicationStatus.PENDING:
                existing.scheduled_for = scheduled_for
            return existing

        item = PublicationQueueItem(
            article_id=article.id,
            market=market,
            target=str(target),
            channel=self.channel_for(market, target),
            idempotency_key=key,
            status=PublicationStatus.PENDING,
            scheduled_for=scheduled_for or utcnow(),
            article_version=article.current_version,
        )
        self.session.add(item)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            found = self.session.scalar(
                select(PublicationQueueItem).where(PublicationQueueItem.idempotency_key == key)
            )
            if found is None:
                raise
            return found
        return item

    def claim(self, item: PublicationQueueItem, worker_id: str) -> bool:
        """Take exclusive ownership of a queue row."""
        now = utcnow()
        if item.status == PublicationStatus.IN_PROGRESS:
            if item.locked_at is not None and now - item.locked_at < CLAIM_TTL:
                return False
            log.warning(
                "publisher.reclaiming_stale_lock", queue_id=item.id, previous=item.locked_by
            )
        if item.status in {PublicationStatus.PUBLISHED, PublicationStatus.CANCELLED}:
            return False
        item.status = PublicationStatus.IN_PROGRESS
        item.locked_at = now
        item.locked_by = worker_id
        item.attempts += 1
        self.session.flush()
        return True

    # ------------------------------------------------------------ publishing
    def publish(
        self,
        article: Article,
        rich_message: dict[str, Any],
        *,
        target: PublicationTarget | str = PublicationTarget.PRODUCTION,
        queue_item: PublicationQueueItem | None = None,
        worker_id: str | None = None,
    ) -> PublicationResult:
        market: Market = article.market  # type: ignore[assignment]
        key = idempotency_key(article.id, article.current_version, str(target))

        existing = self.session.scalar(
            select(TelegramPublication).where(TelegramPublication.idempotency_key == key)
        )
        if existing is not None:
            log.info("publisher.already_published", article_id=article.id, key=key)
            return PublicationResult(existing, created=False, reused=True)

        errors = validate_rich_message(rich_message)
        if errors:
            raise TelegramValidationError("; ".join(errors))

        channel = self.channel_for(market, target)
        worker_id = worker_id or new_job_id("worker")

        if queue_item is not None and not self.claim(queue_item, worker_id):
            raise DuplicatePublication(
                f"queue item {queue_item.id} is already being processed or finished"
            )

        try:
            sent = self.client.send_rich_message(channel, rich_message)
        except TelegramRateLimited:
            if queue_item is not None:
                queue_item.status = PublicationStatus.PENDING
                queue_item.locked_at = None
                queue_item.locked_by = None
                self.session.flush()
            raise
        except TelegramValidationError as exc:
            if queue_item is not None:
                queue_item.status = PublicationStatus.FAILED
                queue_item.last_error = str(exc)
                self.session.flush()
            article.status = ArticleStatus.FAILED
            article.status_reason = str(exc)
            raise
        except TelegramError as exc:
            # The request may or may not have reached Telegram. Leave the row claimed
            # so nothing republishes it blindly; reconciliation resolves it.
            if queue_item is not None:
                queue_item.last_error = f"unknown outcome: {exc}"
                if queue_item.attempts >= MAX_PUBLISH_ATTEMPTS:
                    queue_item.status = PublicationStatus.FAILED
                self.session.flush()
            log.error("publisher.unknown_outcome", article_id=article.id, error=str(exc))
            raise

        publication = TelegramPublication(
            idempotency_key=key,
            market=market,
            target=str(target),
            chat_id=sent.chat_id,
            channel_username=channel,
            message_id=sent.message_id,
            message_url=sent.url,
            article_version=article.current_version,
            telegram_response=sent.raw,
        )
        article.publications.append(publication)

        if str(target) == PublicationTarget.PRODUCTION:
            article.status = ArticleStatus.PUBLISHED
            article.published_at = utcnow()
        if queue_item is not None:
            queue_item.status = PublicationStatus.PUBLISHED
            queue_item.last_error = None
        self.session.flush()

        log.info(
            "publisher.published",
            article_id=article.id,
            market=market,
            target=str(target),
            channel=channel,
            message_id=sent.message_id,
        )
        return PublicationResult(publication, created=True)

    def edit(
        self,
        publication: TelegramPublication,
        rich_message: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        errors = validate_rich_message(rich_message)
        if errors:
            raise TelegramValidationError("; ".join(errors))
        self.client.edit_rich_message(
            publication.chat_id or publication.channel_username,
            publication.message_id or 0,
            rich_message,
        )
        publication.edited_at = utcnow()
        publication.edit_count += 1
        self.session.flush()
        log.info(
            "publisher.edited",
            article_id=publication.article_id,
            message_id=publication.message_id,
            reason=reason,
        )

    def has_published(
        self, article: Article, target: PublicationTarget | str = PublicationTarget.PRODUCTION
    ) -> bool:
        key = idempotency_key(article.id, article.current_version, str(target))
        return (
            self.session.scalar(
                select(TelegramPublication).where(TelegramPublication.idempotency_key == key)
            )
            is not None
        )


__all__ = [
    "CLAIM_TTL",
    "MAX_PUBLISH_ATTEMPTS",
    "PublicationResult",
    "TelegramClientProtocol",
    "TelegramPublisher",
    "idempotency_key",
]
