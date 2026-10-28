"""Native Telegram payloads by PostFormat (spec §5 / §19.9)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleMedia, EditorialPlanSlot

RICH_FORMATS = frozenset({"rich_guide", "museum_spotlight"})
POLL_FORMATS = frozenset({"poll"})
PHOTO_FORMATS = frozenset({"visual_carousel", "story_post"})


@dataclass(slots=True)
class NativePayload:
    method: str
    format: str
    rich_message: dict[str, Any] | None = None
    text: str | None = None
    photo: str | None = None
    caption: str | None = None
    question: str | None = None
    options: list[str] | None = None


def slot_for_article(session: Session, article: Article) -> EditorialPlanSlot | None:
    return session.scalar(
        select(EditorialPlanSlot)
        .where(EditorialPlanSlot.article_id == article.id)
        .order_by(EditorialPlanSlot.id.desc())
    )


def format_for_article(session: Session, article: Article) -> str:
    slot = slot_for_article(session, article)
    if slot is not None:
        return slot.format
    editorial = (article.quality_scores or {}).get("editorial") or {}
    if isinstance(editorial, dict) and editorial.get("format"):
        return str(editorial["format"])
    return "rich_guide"


def article_plain_text(article: Article, *, limit: int = 3900) -> str:
    body = article.body if isinstance(article.body, dict) else {}
    parts: list[str] = []
    title = body.get("title") or article.title
    intro = body.get("intro")
    if title:
        parts.append(str(title).strip())
    if intro:
        parts.append(str(intro).strip())
    for section in body.get("sections") or []:
        if not isinstance(section, dict):
            continue
        heading = section.get("heading")
        if heading:
            parts.append(str(heading).strip())
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if text:
                parts.append(str(text).strip())
            for item in block.get("items") or []:
                parts.append(f"• {item}")
    text = "\n\n".join(part for part in parts if part)
    return text[:limit]


def first_media_url(article: Article) -> str | None:
    for row in article.media or []:
        if isinstance(row, ArticleMedia) and row.url:
            return row.url
    body = article.body if isinstance(article.body, dict) else {}
    for item in body.get("media") or []:
        if isinstance(item, dict) and item.get("url"):
            return str(item["url"])
    return None


def poll_question_and_options(article: Article) -> tuple[str, list[str]]:
    body = article.body if isinstance(article.body, dict) else {}
    question = str(body.get("title") or article.title or "What should we cover next?")[:300]
    options: list[str] = []
    for section in body.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "list":
                options.extend(str(item)[:100] for item in (block.get("items") or []))
    options = [item.strip() for item in options if str(item).strip()]
    if len(options) < 2:
        if article.market == "ru":
            options = ["В эти выходные", "Поездка на пару дней", "Музей / выставка"]
        else:
            options = ["This weekend", "A short trip", "A museum day"]
    return question, options[:10]


def native_payload(session: Session, article: Article) -> NativePayload:
    fmt = format_for_article(session, article)
    if fmt in POLL_FORMATS:
        question, options = poll_question_and_options(article)
        return NativePayload(method="sendPoll", format=fmt, question=question, options=options)
    if fmt in PHOTO_FORMATS:
        photo = first_media_url(article)
        if photo:
            caption = article_plain_text(article, limit=1024)
            return NativePayload(method="sendPhoto", format=fmt, photo=photo, caption=caption)
        return NativePayload(method="sendMessage", format=fmt, text=article_plain_text(article))
    if fmt in RICH_FORMATS:
        rich = article.rendered_message if isinstance(article.rendered_message, dict) else None
        return NativePayload(method="sendRichMessage", format=fmt, rich_message=rich)
    return NativePayload(method="sendMessage", format=fmt, text=article_plain_text(article))


__all__ = [
    "NativePayload",
    "PHOTO_FORMATS",
    "POLL_FORMATS",
    "RICH_FORMATS",
    "format_for_article",
    "native_payload",
    "slot_for_article",
]
