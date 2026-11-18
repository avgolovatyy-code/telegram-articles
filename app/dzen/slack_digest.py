"""One weekday Slack digest, exactly one staff mention, never on weekends."""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.enums import DzenArticleStatus
from app.db.models import DzenArticle, DzenHandoffBatch, DzenHandoffItem, DzenPublishingKit
from app.db.types import utcnow
from app.dzen.kit import kit_is_expired, public_kit_path
from app.dzen.policy import (
    local_now,
    may_send_staff_digest,
    mention_markup,
    resolved_slack_channel,
)
from app.logging_setup import get_logger
from app.slack.client import SlackError, SlackMessage, build_slack_client

log = get_logger("dzen.slack")


@dataclass(slots=True)
class DigestReport:
    ok: bool = True
    sent: bool = False
    reason: str = ""
    item_count: int = 0
    slack_ts: str | None = None
    mentioned: bool = False


def _ready_kits(session: Session, now: dt.datetime) -> list[tuple[DzenArticle, DzenPublishingKit]]:
    rows = session.scalars(
        select(DzenArticle).where(DzenArticle.status == DzenArticleStatus.READY_FOR_HANDOFF.value)
    ).all()
    result: list[tuple[DzenArticle, DzenPublishingKit]] = []
    for article in rows:
        kit = session.scalar(
            select(DzenPublishingKit)
            .where(
                DzenPublishingKit.article_id == article.id,
                DzenPublishingKit.stale.is_(False),
            )
            .order_by(DzenPublishingKit.id.desc())
        )
        if kit is None or kit_is_expired(kit, now):
            continue
        if not kit.cover_url or not kit.html_body:
            continue
        already = session.scalar(
            select(DzenHandoffItem.id).where(
                DzenHandoffItem.article_id == article.id,
                DzenHandoffItem.article_version == article.version,
            )
        )
        if already is not None:
            continue
        result.append((article, kit))
    return result


def _pings_today(session: Session, local_date: dt.date, staff_user_id: str, channel: str) -> int:
    return len(
        session.scalars(
            select(DzenHandoffBatch).where(
                DzenHandoffBatch.local_work_date == local_date,
                DzenHandoffBatch.staff_user_id == staff_user_id,
                DzenHandoffBatch.slack_channel_id == channel,
                DzenHandoffBatch.slack_message_ts.is_not(None),
            )
        ).all()
    )


def _last_send_date(session: Session, staff_user_id: str, channel: str) -> dt.date | None:
    row = session.scalar(
        select(DzenHandoffBatch.local_work_date)
        .where(
            DzenHandoffBatch.staff_user_id == staff_user_id,
            DzenHandoffBatch.slack_channel_id == channel,
            DzenHandoffBatch.slack_message_ts.is_not(None),
        )
        .order_by(DzenHandoffBatch.local_work_date.desc())
    )
    return row


def _batch_for_day(
    session: Session, local_date: dt.date, staff_user_id: str, channel: str
) -> DzenHandoffBatch | None:
    return session.scalar(
        select(DzenHandoffBatch).where(
            DzenHandoffBatch.local_work_date == local_date,
            DzenHandoffBatch.staff_user_id == staff_user_id,
            DzenHandoffBatch.slack_channel_id == channel,
        )
    )


def build_digest_blocks(
    items: list[tuple[DzenArticle, DzenPublishingKit]],
    *,
    settings: Settings,
    admin_root: str,
) -> tuple[list[dict[str, Any]], str]:
    mention = mention_markup(settings)
    count = len(items)
    header = f"📝 WeGoTrip / Дзен — готовы статьи к публикации ({count})"
    intro = (
        f"{mention} Привет! Подготовили материалы, можно перенести в Дзен через готовые пакеты:"
        if mention
        else "Готовы материалы для переноса в Дзен:"
    )
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text": intro}},
    ]
    fallback_lines = [header, intro, ""]
    for index, (article, kit) in enumerate(items, start=1):
        kit_url = admin_root.rstrip("/") + public_kit_path(kit)
        cover = kit.cover_url or ""
        images = len(kit.media_manifest_json or [])
        products = len(kit.product_links_json or [])
        checked = (kit.ready_at or utcnow()).date().isoformat()
        title = (article.headline or "Статья")[:180]
        body = (
            f"*{index}) {title}*\n"
            f"<{kit_url}|Открыть готовую статью>\n"
            f"Обложка: {cover}\n"
            f"Иллюстрации: {images} • Товары: {products} • Проверено: {checked}"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}})
        fallback_lines.append(f"{index}) {title}\n{kit_url}\nОбложка: {cover}")
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "После публикации отправь ссылку dzen.ru/a/... ответом в этот тред "
                        "(если статей несколько — `1: URL`). Либо вставь URL в Publishing Kit."
                    ),
                }
            ],
        }
    )
    fallback_lines.append("После публикации ответь ссылкой dzen.ru/a/... в этот тред.")
    return blocks, "\n".join(fallback_lines)


def send_dzen_digest(
    session: Session,
    *,
    settings: Settings | None = None,
    client: Any | None = None,
    now: dt.datetime | None = None,
    force_hour: bool = False,
) -> DigestReport:
    settings = settings or get_settings()
    report = DigestReport()
    if settings.dzen_native_autopublish_enabled:
        report.ok = False
        report.reason = "native_autopublish_forbidden"
        return report

    local = local_now(settings, now)
    channel = resolved_slack_channel(settings)
    staff = (settings.dzen_slack_mention_user_id or "").strip()
    if not channel:
        report.reason = "channel_unresolved"
        return report

    existing = _batch_for_day(session, local.date(), staff, channel)
    if existing is not None and existing.slack_message_ts:
        report.reason = "already_sent_today"
        report.slack_ts = existing.slack_message_ts
        return report

    # Hard weekend lock: never construct a Slack send call.
    allowed, reason = may_send_staff_digest(
        settings,
        now=now,
        last_send_date=_last_send_date(session, staff, channel),
        pings_today=_pings_today(session, local.date(), staff, channel),
        force_hour=force_hour,
    )
    if not allowed:
        report.reason = reason
        return report

    pairs = _ready_kits(session, utcnow())
    if not pairs:
        report.reason = "empty_queue"
        return report

    admin_root = settings.tracking_root
    blocks, fallback = build_digest_blocks(pairs, settings=settings, admin_root=admin_root)
    mention_present = mention_markup(settings) in fallback
    if fallback.count("<@") > 1:
        report.ok = False
        report.reason = "mention_budget_builder"
        return report

    slack = client or build_slack_client(settings)
    batch = existing or DzenHandoffBatch(
        public_id=secrets.token_urlsafe(8),
        local_work_date=local.date(),
        timezone=str(local.tzinfo),
        slack_channel_id=channel,
        staff_user_id=staff,
        item_count=len(pairs),
        status="pending",
    )
    if existing is None:
        session.add(batch)
        session.flush()

    try:
        posted: SlackMessage = slack.post_message(blocks=blocks, text=fallback, channel=channel)
    except SlackError as exc:
        batch.status = "failed"
        batch.error = str(exc)[:500]
        report.ok = False
        report.reason = "slack_error"
        log.error("dzen.digest.slack_failed", error=str(exc))
        return report

    if not posted.ts:
        batch.status = "failed"
        batch.error = "empty ts"
        report.ok = False
        report.reason = "empty_ts"
        return report

    batch.slack_message_ts = posted.ts
    batch.slack_thread_ts = posted.ts
    batch.item_count = len(pairs)
    batch.status = "sent"
    batch.sent_at = utcnow()
    batch.error = None
    for position, (article, _kit) in enumerate(pairs, start=1):
        session.add(
            DzenHandoffItem(
                batch_id=batch.id,
                article_id=article.id,
                article_version=article.version,
                position=position,
                status=DzenArticleStatus.HANDED_OFF.value,
            )
        )
        article.status = DzenArticleStatus.HANDED_OFF.value
        article.handed_off_at = utcnow()
    session.flush()
    report.sent = True
    report.item_count = len(pairs)
    report.slack_ts = posted.ts
    report.mentioned = mention_present
    report.reason = "ok"
    log.info(
        "dzen.digest.sent",
        count=len(pairs),
        channel=channel,
        local_date=str(local.date()),
        mentioned=mention_present,
    )
    return report


__all__ = ["DigestReport", "build_digest_blocks", "send_dzen_digest"]
