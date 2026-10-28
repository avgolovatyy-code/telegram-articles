"""Article JSON → Max-native post (never Telegram InputRichMessage).

Telegram keeps ``sendRichMessage`` with block-based ``InputRichMessage``.
Max has no rich-block API, so the same ``article.body`` is rendered here into a
short Max post: markdown text (≤4000 chars) + product link buttons.
"""

from __future__ import annotations

from html import escape as html_escape
from typing import Any

from app.config import Settings, get_settings
from app.db.models import Article
from app.generation.schemas import ArticleDocument
from app.links.affiliate import AffiliateLinkBuilder, LinkContext

MAX_TEXT_CHARS = 4000
#: Leave room for a trailing products section / ellipsis.
BODY_BUDGET = 3200
MAX_PRODUCT_BUTTONS = 6

#: Max supports both markdown and html; html gives clearer headings/lists.
MAX_FORMAT = "html"


def _md_escape(text: str) -> str:
    """Escape characters that commonly break Max markdown without killing URLs."""
    return (
        text.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _html_escape(text: str) -> str:
    return html_escape(text, quote=True)


def _section_parts_html(document: ArticleDocument) -> list[str]:
    parts: list[str] = []
    if document.intro.strip():
        parts.append(f"<p>{_html_escape(document.intro.strip())}</p>")
    for section in document.sections:
        heading = section.heading.strip()
        if heading:
            parts.append(f"<h2>{_html_escape(heading)}</h2>")
        for block in section.blocks:
            if block.text and block.text.strip():
                parts.append(f"<p>{_html_escape(block.text.strip())}</p>")
            if block.items:
                items = "".join(
                    f"<li>{_html_escape(item.strip())}</li>" for item in block.items if item.strip()
                )
                if items:
                    parts.append(f"<ul>{items}</ul>")
            for row in block.rows:
                joined = " | ".join(cell.strip() for cell in row if cell and cell.strip())
                if joined:
                    parts.append(f"<p>{_html_escape(joined)}</p>")
    if document.closing and document.closing.strip():
        parts.append(f"<p>{_html_escape(document.closing.strip())}</p>")
    return parts


def _section_parts_markdown(document: ArticleDocument) -> list[str]:
    parts: list[str] = []
    if document.intro.strip():
        parts.append(document.intro.strip())
    for section in document.sections:
        heading = section.heading.strip()
        if heading:
            parts.append(f"**{_md_escape(heading)}**")
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


def _fit(parts: list[str], budget: int, *, joiner: str = "\n\n") -> str:
    out: list[str] = []
    used = 0
    sep_len = len(joiner)
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        extra = len(chunk) + (sep_len if out else 0)
        if used + extra > budget:
            remaining = budget - used - (sep_len if out else 0)
            if remaining > 40:
                # Avoid cutting inside an unclosed HTML tag when possible.
                clipped = chunk[: remaining - 1].rstrip()
                if "<" in clipped and clipped.rfind("<") > clipped.rfind(">"):
                    clipped = clipped[: clipped.rfind("<")].rstrip()
                if clipped:
                    out.append(clipped + "…")
            break
        out.append(chunk)
        used += extra
    return joiner.join(out)


def _max_product_url(url: str, article: Article, settings: Settings) -> str:
    """Force ``coupon`` + ``utm_source=max`` without inheriting Telegram UTM."""
    builder = AffiliateLinkBuilder(settings)
    if not builder.is_store_url(url):
        return url
    ctx = LinkContext(
        market="ru",
        article_id=str(article.id) if article.id is not None else article.public_id,
        topic_slug=article.topic_slug,
        utm_source=settings.maxapp_utm_source or "max",
        utm_medium="organic_social",
        utm_campaign="editorial_ru",
    )
    return builder.decorate(url, ctx)


def render_max_payload(
    article: Article,
    *,
    settings: Settings | None = None,
    document: ArticleDocument | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Build Max ``POST /messages`` body fields (text + attachments).

    Uses an adapted ``ArticleDocument`` when provided; otherwise reads
    ``article.body`` only — never ``article.rendered_message`` (Telegram).
    """
    settings = settings or get_settings()
    if document is None:
        if not article.body:
            raise ValueError("article has no body")
        document = ArticleDocument.model_validate(article.body)
    title = (title or article.title or document.title or "").strip() or "WeGoTrip"

    if MAX_FORMAT == "html":
        body = _fit(_section_parts_html(document), BODY_BUDGET)
        text = f"<h1>{_html_escape(title)}</h1>"
        if body:
            text = f"{text}\n{body}"
        footer = "\n<p>Билеты и аудиогиды — в кнопках ниже.</p>"
    else:
        body = _fit(_section_parts_markdown(document), BODY_BUDGET)
        text = f"# {_md_escape(title)}"
        if body:
            text = f"{text}\n\n{body}"
        footer = "\n\nБилеты и аудиогиды — в кнопках ниже."

    buttons: list[list[dict[str, str]]] = []
    for ap in sorted(article.products, key=lambda p: (p.position, p.id)):
        if not ap.active:
            continue
        raw_url = (ap.affiliate_url or ap.tracking_url or "").strip()
        if not raw_url:
            continue
        url = _max_product_url(raw_url, article, settings)
        snap = ap.snapshot if isinstance(ap.snapshot, dict) else {}
        label = str(snap.get("title") or snap.get("name") or "WeGoTrip").strip()
        if len(label) > 64:
            label = label[:61] + "…"
        buttons.append([{"type": "link", "text": label, "url": url}])
        if len(buttons) >= MAX_PRODUCT_BUTTONS:
            break

    if buttons:
        if len(text) + len(footer) > MAX_TEXT_CHARS:
            text = text[: MAX_TEXT_CHARS - len(footer) - 1].rstrip() + "…"
        text = text + footer
    elif len(text) > MAX_TEXT_CHARS:
        text = text[: MAX_TEXT_CHARS - 1].rstrip() + "…"

    payload: dict[str, Any] = {"text": text, "format": MAX_FORMAT}
    if buttons:
        payload["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
    return payload


__all__ = ["MAX_FORMAT", "MAX_TEXT_CHARS", "render_max_payload"]
