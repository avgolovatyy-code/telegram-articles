"""Article JSON → Max markdown post (≤4000 chars) + product link buttons."""

from __future__ import annotations

from typing import Any

from app.db.models import Article
from app.generation.schemas import ArticleDocument

MAX_TEXT_CHARS = 4000
#: Leave room for a trailing products section / ellipsis.
BODY_BUDGET = 3200
MAX_PRODUCT_BUTTONS = 6


def _markdown_escape_lite(text: str) -> str:
    """Escape characters that commonly break Max markdown without killing URLs."""
    return (
        text.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _section_plain(document: ArticleDocument) -> list[str]:
    parts: list[str] = []
    if document.intro.strip():
        parts.append(document.intro.strip())
    for section in document.sections:
        heading = section.heading.strip()
        if heading:
            parts.append(f"**{heading}**")
        for block in section.blocks:
            if block.text and block.text.strip():
                parts.append(block.text.strip())
            if block.items:
                parts.extend(f"• {item.strip()}" for item in block.items if item.strip())
            for row in block.rows:
                joined = " | ".join(cell.strip() for cell in row if cell and cell.strip())
                if joined:
                    parts.append(joined)
    if document.closing and document.closing.strip():
        parts.append(document.closing.strip())
    return parts


def _fit(parts: list[str], budget: int) -> str:
    out: list[str] = []
    used = 0
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        extra = len(chunk) + (2 if out else 0)
        if used + extra > budget:
            remaining = budget - used - (2 if out else 0)
            if remaining > 40:
                out.append(chunk[: remaining - 1].rstrip() + "…")
            break
        out.append(chunk)
        used += extra
    return "\n\n".join(out)


def render_max_payload(article: Article) -> dict[str, Any]:
    """Build Max ``POST /messages`` body fields (text + attachments)."""
    if not article.body:
        raise ValueError("article has no body")
    document = ArticleDocument.model_validate(article.body)
    title = (article.title or document.title or "").strip() or "WeGoTrip"
    body = _fit(_section_plain(document), BODY_BUDGET)
    text = f"**{_markdown_escape_lite(title)}**"
    if body:
        text = f"{text}\n\n{body}"

    buttons: list[list[dict[str, str]]] = []
    for ap in sorted(article.products, key=lambda p: (p.position, p.id)):
        if not ap.active:
            continue
        url = (ap.tracking_url or ap.affiliate_url or "").strip()
        if not url:
            continue
        snap = ap.snapshot if isinstance(ap.snapshot, dict) else {}
        label = str(snap.get("title") or snap.get("name") or "WeGoTrip").strip()
        if len(label) > 64:
            label = label[:61] + "…"
        buttons.append([{"type": "link", "text": label, "url": url}])
        if len(buttons) >= MAX_PRODUCT_BUTTONS:
            break

    if buttons:
        footer = "\n\nБилеты и аудиогиды — в кнопках ниже."
        if len(text) + len(footer) > MAX_TEXT_CHARS:
            text = text[: MAX_TEXT_CHARS - len(footer) - 1].rstrip() + "…"
        text = text + footer
    elif len(text) > MAX_TEXT_CHARS:
        text = text[: MAX_TEXT_CHARS - 1].rstrip() + "…"

    payload: dict[str, Any] = {"text": text, "format": "markdown"}
    if buttons:
        payload["attachments"] = [
            {"type": "inline_keyboard", "payload": {"buttons": buttons}}
        ]
    return payload


__all__ = ["MAX_TEXT_CHARS", "render_max_payload"]
