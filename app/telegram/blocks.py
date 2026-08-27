"""Builders for Telegram ``InputRichBlock`` payloads (Bot API 10.x).

Only the official Bot API shapes are produced here — no userbot, no HTML/Markdown
guessing. Every helper returns a plain dict ready to be JSON-serialised into
``sendRichMessage``.

Limits enforced by :func:`validate_rich_message`:
32768 characters, 500 blocks (including nested), 50 media attachments, 20 table columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RichText = str | dict[str, Any] | list[Any]

CHAR_LIMIT = 32768
BLOCK_LIMIT = 500
MEDIA_LIMIT = 50
TABLE_COLUMN_LIMIT = 20
BUTTONS_PER_ROW_LIMIT = 8


# ------------------------------------------------------------------ rich text
def bold(text: RichText) -> dict[str, Any]:
    return {"type": "bold", "text": text}


def italic(text: RichText) -> dict[str, Any]:
    return {"type": "italic", "text": text}


def marked(text: RichText) -> dict[str, Any]:
    return {"type": "marked", "text": text}


def link(text: RichText, url: str) -> dict[str, Any]:
    return {"type": "url", "text": text, "url": url}


def hashtag(tag: str) -> dict[str, Any]:
    value = tag if tag.startswith("#") else f"#{tag}"
    return {"type": "hashtag", "text": value, "hashtag": value}


# --------------------------------------------------------------------- blocks
def paragraph(text: RichText) -> dict[str, Any]:
    return {"type": "paragraph", "text": text}


def heading(text: RichText, size: int = 2) -> dict[str, Any]:
    return {"type": "heading", "text": text, "size": max(1, min(6, size))}


def divider() -> dict[str, Any]:
    return {"type": "divider"}


def footer(text: RichText) -> dict[str, Any]:
    return {"type": "footer", "text": text}


def bullet_list(items: list[RichText]) -> dict[str, Any]:
    return {
        "type": "list",
        "items": [{"blocks": [paragraph(item)]} for item in items],
    }


def ordered_list(items: list[RichText]) -> dict[str, Any]:
    return {
        "type": "list",
        "items": [
            {"blocks": [paragraph(item)], "value": index + 1, "type": "1"}
            for index, item in enumerate(items)
        ],
    }


def blockquote(blocks: list[dict[str, Any]], credit: RichText | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "blockquote", "blocks": blocks}
    if credit:
        payload["credit"] = credit
    return payload


def expandable_blockquote(text: RichText, credit: RichText | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "expandable_blockquote", "text": text}
    if credit:
        payload["credit"] = credit
    return payload


def pull_quote(text: RichText, credit: RichText | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "pullquote", "text": text}
    if credit:
        payload["credit"] = credit
    return payload


def table(
    rows: list[list[RichText]], *, bordered: bool = True, caption: RichText | None = None
) -> dict[str, Any]:
    cells = [[{"text": cell} for cell in row[:TABLE_COLUMN_LIMIT]] for row in rows]
    payload: dict[str, Any] = {"type": "table", "cells": cells}
    if bordered:
        payload["is_bordered"] = True
    if caption:
        payload["caption"] = caption
    return payload


def details(
    summary: RichText, blocks: list[dict[str, Any]], *, is_open: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "details", "summary": summary, "blocks": blocks}
    if is_open:
        payload["is_open"] = True
    return payload


def photo(url: str, caption: RichText | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "photo", "photo": {"type": "photo", "media": url}}
    if caption:
        payload["caption"] = {"text": caption}
    return payload


def collage(urls: list[str], caption: RichText | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "collage",
        "blocks": [photo(url) for url in urls],
    }
    if caption:
        payload["caption"] = {"text": caption}
    return payload


def slideshow(urls: list[str], caption: RichText | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "slideshow",
        "blocks": [photo(url) for url in urls],
    }
    if caption:
        payload["caption"] = {"text": caption}
    return payload


def audio(
    url: str,
    *,
    title: str | None = None,
    performer: str | None = None,
    caption: RichText | None = None,
) -> dict[str, Any]:
    media: dict[str, Any] = {"type": "audio", "media": url}
    if title:
        media["title"] = title
    if performer:
        media["performer"] = performer
    payload: dict[str, Any] = {"type": "audio", "audio": media}
    if caption:
        payload["caption"] = {"text": caption}
    return payload


def voice_note(url: str, caption: RichText | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "voice_note",
        "voice_note": {"type": "voice_note", "media": url},
    }
    if caption:
        payload["caption"] = {"text": caption}
    return payload


def url_button(text: str, url: str, *, style: str = "primary") -> dict[str, Any]:
    return {"text": text, "url": url, "style": style}


def buttons(items: list[dict[str, Any]], *, align: str = "left") -> dict[str, Any]:
    return {"type": "buttons", "buttons": items[:BUTTONS_PER_ROW_LIMIT], "align": align}


def rich_message(blocks: list[dict[str, Any]], *, is_rtl: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {"blocks": blocks}
    if is_rtl:
        payload["is_rtl"] = True
    return payload


# ----------------------------------------------------------------- validation
@dataclass(slots=True)
class RichMessageStats:
    characters: int
    blocks: int
    media: int
    max_depth: int


_MEDIA_TYPES = {"photo", "video", "animation", "audio", "voice_note", "document"}


def _walk(block: Any, depth: int, stats: dict[str, int]) -> None:
    if isinstance(block, dict):
        if "type" in block and block["type"] not in {"bold", "italic", "url", "hashtag", "marked"}:
            stats["blocks"] += 1
            if block["type"] in _MEDIA_TYPES:
                stats["media"] += 1
        stats["max_depth"] = max(stats["max_depth"], depth)
        for key, value in block.items():
            if key == "type":
                continue
            _walk(value, depth + 1, stats)
    elif isinstance(block, list):
        for item in block:
            _walk(item, depth + 1, stats)
    elif isinstance(block, str):
        stats["characters"] += len(block)


def message_stats(message: dict[str, Any]) -> RichMessageStats:
    stats = {"characters": 0, "blocks": 0, "media": 0, "max_depth": 0}
    for block in message.get("blocks", []):
        _walk(block, 1, stats)
    return RichMessageStats(
        characters=stats["characters"],
        blocks=stats["blocks"],
        media=stats["media"],
        max_depth=stats["max_depth"],
    )


def validate_rich_message(message: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    blocks = message.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return ["rich message has no blocks"]

    stats = message_stats(message)
    if stats.characters > CHAR_LIMIT:
        errors.append(f"rich message text {stats.characters} > {CHAR_LIMIT} characters")
    if stats.blocks > BLOCK_LIMIT:
        errors.append(f"rich message has {stats.blocks} blocks > {BLOCK_LIMIT}")
    if stats.media > MEDIA_LIMIT:
        errors.append(f"rich message has {stats.media} media > {MEDIA_LIMIT}")
    if stats.max_depth > 16:
        errors.append(f"nesting depth {stats.max_depth} > 16")

    for block in blocks:
        if not isinstance(block, dict) or "type" not in block:
            errors.append("a block is missing its type")
            continue
        if block["type"] == "table":
            for row in block.get("cells", []):
                if len(row) > TABLE_COLUMN_LIMIT:
                    errors.append(f"table row has {len(row)} columns > {TABLE_COLUMN_LIMIT}")
                    break
        if block["type"] == "buttons" and len(block.get("buttons", [])) > BUTTONS_PER_ROW_LIMIT:
            errors.append("a button row has more than 8 buttons")
    return errors


def collect_urls(message: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "url" and isinstance(value, str):
                    urls.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(message)
    return urls


def collect_media_urls(message: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") in _MEDIA_TYPES and isinstance(node.get("media"), str):
                urls.append(node["media"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(message)
    return urls


__all__ = [
    "BLOCK_LIMIT",
    "BUTTONS_PER_ROW_LIMIT",
    "CHAR_LIMIT",
    "MEDIA_LIMIT",
    "TABLE_COLUMN_LIMIT",
    "RichMessageStats",
    "audio",
    "blockquote",
    "bold",
    "bullet_list",
    "buttons",
    "collage",
    "collect_media_urls",
    "collect_urls",
    "details",
    "divider",
    "expandable_blockquote",
    "footer",
    "hashtag",
    "heading",
    "italic",
    "link",
    "marked",
    "message_stats",
    "ordered_list",
    "paragraph",
    "photo",
    "pull_quote",
    "rich_message",
    "slideshow",
    "table",
    "url_button",
    "validate_rich_message",
    "voice_note",
]
