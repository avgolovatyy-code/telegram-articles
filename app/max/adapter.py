"""Adapt a verified RU article into a Max-native short post (addendum §7–8).

This is **not** a Telegram Rich Message trim and **not** a second fact-finding
pass. It reuses the article body / claims already verified for Telegram RU and
rewrites them into a shorter Max-shaped document (≈400–1200 chars target).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models import Article
from app.generation.schemas import ArticleBlock, ArticleDocument, ArticleSection

#: Soft target for ordinary Max posts (chars of plain text, not HTML).
MAX_SOFT_CHARS = 1200
MAX_HARD_CHARS = 2500


@dataclass(slots=True)
class AdaptedMaxPost:
    title: str
    document: ArticleDocument
    char_estimate: int
    adapted: bool
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "char_estimate": self.char_estimate,
            "adapted": self.adapted,
            "rationale": self.rationale,
        }


def _plain_len(document: ArticleDocument, title: str) -> int:
    parts = [title, document.intro or ""]
    for section in document.sections:
        parts.append(section.heading or "")
        for block in section.blocks:
            if block.text:
                parts.append(block.text)
            parts.extend(block.items or [])
    if document.closing:
        parts.append(document.closing)
    return sum(len(p) for p in parts if p)


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rstrip()
    # Prefer sentence boundary.
    for sep in (". ", "! ", "? ", "。"):
        idx = cut.rfind(sep)
        if idx >= 40:
            return cut[: idx + 1].strip()
    return cut + "…"


def adapt_for_max(article: Article) -> AdaptedMaxPost:
    """Build a Max-oriented ArticleDocument from the stored RU article body."""
    if not article.body:
        raise ValueError("article has no body to adapt for Max")
    source = ArticleDocument.model_validate(article.body)
    title = (article.title or source.title or "WeGoTrip").strip()
    original_len = _plain_len(source, title)

    # Already short enough — keep structure, still mark as Max-adapted copy.
    if original_len <= MAX_SOFT_CHARS:
        doc = source.model_copy(deep=True)
        doc.title = title
        return AdaptedMaxPost(
            title=title,
            document=doc,
            char_estimate=original_len,
            adapted=True,
            rationale="body already within Max soft length; reused verified text",
        )

    intro = _clip(source.intro or "", 280)
    sections: list[ArticleSection] = []
    budget = MAX_SOFT_CHARS - len(title) - len(intro) - len(source.closing or "")
    for section in source.sections[:3]:
        if budget < 80:
            break
        blocks: list[ArticleBlock] = []
        for block in section.blocks:
            if block.type in {"divider"}:
                continue
            if block.text:
                chunk = _clip(block.text, min(220, budget))
                if chunk:
                    blocks.append(ArticleBlock(type="paragraph", text=chunk))
                    budget -= len(chunk)
            if block.items:
                items = [item.strip() for item in block.items if item and item.strip()][:4]
                if items:
                    blocks.append(ArticleBlock(type="list", items=items))
                    budget -= sum(len(i) for i in items)
            if budget < 80:
                break
        if blocks:
            sections.append(
                ArticleSection(heading=_clip(section.heading, 80), level=2, blocks=blocks)
            )

    closing = _clip(source.closing or "", 160) if source.closing else None
    adapted = ArticleDocument(
        title=title,
        intro=intro,
        sections=sections,
        product_placements=list(source.product_placements or [])[:2],
        media_placements=[],
        audio_placements=[],
        faq=[],
        hashtags=[],
        claims=list(source.claims or []),
        closing=closing,
    )
    return AdaptedMaxPost(
        title=title,
        document=adapted,
        char_estimate=_plain_len(adapted, title),
        adapted=True,
        rationale=(
            f"shortened verified RU body for Max ({original_len}→"
            f"{_plain_len(adapted, title)} chars); no new claims"
        ),
    )


__all__ = ["MAX_HARD_CHARS", "MAX_SOFT_CHARS", "AdaptedMaxPost", "adapt_for_max"]
