"""Render a Telegram rich message to HTML for the admin preview.

This is a faithful-enough approximation for editorial review; the payload sent to
Telegram is always the JSON, never this HTML.
"""

from __future__ import annotations

from html import escape
from typing import Any


def rich_text_to_html(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return escape(node)
    if isinstance(node, list):
        return "".join(rich_text_to_html(item) for item in node)
    if not isinstance(node, dict):
        return escape(str(node))

    kind = node.get("type")
    inner = rich_text_to_html(node.get("text"))
    match kind:
        case "bold":
            return f"<strong>{inner}</strong>"
        case "italic":
            return f"<em>{inner}</em>"
        case "underline":
            return f"<u>{inner}</u>"
        case "strikethrough":
            return f"<s>{inner}</s>"
        case "marked":
            return f"<mark>{inner}</mark>"
        case "code":
            return f"<code>{inner}</code>"
        case "url":
            href = escape(str(node.get("url", "")))
            return f'<a href="{href}" target="_blank" rel="nofollow noopener">{inner}</a>'
        case "hashtag":
            return f'<span class="muted">{inner}</span>'
    return inner


def block_to_html(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    kind = block.get("type")
    caption = block.get("caption") or {}
    caption_html = rich_text_to_html(caption.get("text")) if isinstance(caption, dict) else ""

    match kind:
        case "heading":
            size = int(block.get("size", 2))
            css = "tg-h1" if size == 1 else "tg-h2"
            return f'<div class="{css}">{rich_text_to_html(block.get("text"))}</div>'
        case "paragraph":
            return f'<p class="tg-p">{rich_text_to_html(block.get("text"))}</p>'
        case "footer":
            return f'<div class="tg-footer">{rich_text_to_html(block.get("text"))}</div>'
        case "divider":
            return '<hr class="tg-divider">'
        case "list":
            items = "".join(
                f"<li>{''.join(block_to_html(inner) for inner in item.get('blocks', []))}</li>"
                for item in block.get("items", [])
            )
            ordered = any(item.get("value") for item in block.get("items", []))
            tag = "ol" if ordered else "ul"
            return f"<{tag}>{items}</{tag}>"
        case "blockquote":
            body = "".join(block_to_html(inner) for inner in block.get("blocks", []))
            return f'<div class="tg-quote">{body}</div>'
        case "expandable_blockquote":
            return f'<div class="tg-quote">{rich_text_to_html(block.get("text"))}</div>'
        case "pullquote":
            return f'<div class="tg-quote"><em>{rich_text_to_html(block.get("text"))}</em></div>'
        case "photo":
            url = escape(str((block.get("photo") or {}).get("media", "")))
            return (
                f'<div class="tg-photo"><img src="{url}" loading="lazy" alt="">'
                f'<div class="muted small">{caption_html}</div></div>'
            )
        case "collage" | "slideshow":
            inner = "".join(block_to_html(item) for item in block.get("blocks", []))
            return (
                f'<div class="tg-photo">{inner}<div class="muted small">{caption_html}</div></div>'
            )
        case "audio":
            url = escape(str((block.get("audio") or {}).get("media", "")))
            return f'<div class="tg-photo"><audio controls src="{url}"></audio>{caption_html}</div>'
        case "voice_note":
            url = escape(str((block.get("voice_note") or {}).get("media", "")))
            return f'<div class="tg-photo"><audio controls src="{url}"></audio>{caption_html}</div>'
        case "details":
            body = "".join(block_to_html(inner) for inner in block.get("blocks", []))
            summary = rich_text_to_html(block.get("summary"))
            return f"<details><summary>{summary}</summary>{body}</details>"
        case "table":
            rows = []
            for row in block.get("cells", []):
                cells = "".join(f"<td>{rich_text_to_html(cell.get('text'))}</td>" for cell in row)
                rows.append(f"<tr>{cells}</tr>")
            return f"<table>{''.join(rows)}</table>"
        case "buttons":
            rendered_buttons = []
            for button in block.get("buttons", []):
                href = escape(str(button.get("url", "#")))
                label = rich_text_to_html(button.get("text"))
                rendered_buttons.append(
                    f'<a class="tg-button" href="{href}" target="_blank" '
                    f'rel="nofollow noopener">{label}</a>'
                )
            return f'<div class="tg-buttons">{"".join(rendered_buttons)}</div>'
        case "pre":
            return f"<pre>{rich_text_to_html(block.get('text'))}</pre>"
    return f'<p class="tg-p">{rich_text_to_html(block.get("text"))}</p>'


def render_preview(message: dict[str, Any] | None) -> str:
    if not message or not message.get("blocks"):
        return '<div class="empty">Nothing rendered yet.</div>'
    return "".join(block_to_html(block) for block in message["blocks"])


__all__ = ["block_to_html", "render_preview", "rich_text_to_html"]
