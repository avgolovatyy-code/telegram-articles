"""Idempotent RU cross-platform navigation footer (spec 3.0 §10).

Injected by the renderer/publisher — never by the Writer prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.telegram import blocks as tb

ChannelKind = Literal["telegram_ru", "telegram_en", "max_ru"]

MAX_PUBLIC_URL = "https://max.ru/channel_wegotrip"
TELEGRAM_RU_URL = "https://t.me/wegotrip_ru"

TG_RU_FOOTER_PLAIN = "Ещё мы в MAX — читайте там, где удобнее."
MAX_FOOTER_PLAIN = "Ещё мы в Telegram — читайте там, где удобнее."

TG_RU_FOOTER_HTML = (
    'Ещё мы в <a href="https://max.ru/channel_wegotrip">MAX</a> — читайте там, где удобнее.'
)
MAX_FOOTER_HTML = (
    'Ещё мы в <a href="https://t.me/wegotrip_ru">Telegram</a> — читайте там, где удобнее.'
)

FORBIDDEN_MAX_URL_MARKERS = (
    "id7816636266_bot",
    "max.ru/id",
)

HOLD_UNSUPPORTED = "HOLD_UNSUPPORTED_FORMAT"


@dataclass(slots=True)
class FooterResult:
    channel: ChannelKind
    applied: bool
    skipped: bool
    hold: bool
    reason: str
    category: str = "brand_navigation"
    text_html: str | None = None
    text_plain: str | None = None
    rich_block: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "applied": self.applied,
            "skipped": self.skipped,
            "hold": self.hold,
            "reason": self.reason,
            "category": self.category,
        }


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    low = haystack.casefold()
    return any(item.casefold() in low for item in needles)


def contains_forbidden_max_url(text: str | None) -> bool:
    if not text:
        return False
    return _contains_any(text, FORBIDDEN_MAX_URL_MARKERS)


def footer_already_present(text: str | None, channel: ChannelKind) -> bool:
    if not text:
        return False
    low = text.casefold()
    if channel == "telegram_ru":
        return "max.ru/channel_wegotrip" in low or ("ещё мы в" in low and "max" in low)
    if channel == "max_ru":
        return "t.me/wegotrip_ru" in low or ("ещё мы в" in low and "telegram" in low)
    return "max.ru/channel_wegotrip" in low or "ещё мы в" in low


def ru_cross_promo_in_en(text: str | None) -> bool:
    if not text:
        return False
    low = text.casefold()
    return "max.ru/channel_wegotrip" in low or "ещё мы в" in low or "id7816636266_bot" in low


def telegram_ru_rich_footer_block() -> dict[str, Any]:
    return tb.paragraph(
        ["Ещё мы в ", tb.link("MAX", MAX_PUBLIC_URL), " — читайте там, где удобнее."]
    )


def inject_telegram_rich(message: dict[str, Any] | None, *, market: str) -> FooterResult:
    """Append exactly one clickable footer to a Telegram rich payload."""
    if market != "ru":
        if message and ru_cross_promo_in_en(str(message)):
            return FooterResult(
                channel="telegram_en",
                applied=False,
                skipped=True,
                hold=True,
                reason="EN payload contains RU cross-promo footer",
            )
        return FooterResult(
            channel="telegram_en",
            applied=False,
            skipped=True,
            hold=False,
            reason="EN has no RU footer",
        )
    if not isinstance(message, dict):
        return FooterResult(
            channel="telegram_ru",
            applied=False,
            skipped=True,
            hold=True,
            reason=HOLD_UNSUPPORTED,
        )
    blob = str(message)
    if contains_forbidden_max_url(blob):
        return FooterResult(
            channel="telegram_ru",
            applied=False,
            skipped=True,
            hold=True,
            reason="legacy MAX URL in payload",
        )
    blocks = message.setdefault("blocks", [])
    if not isinstance(blocks, list):
        return FooterResult(
            channel="telegram_ru",
            applied=False,
            skipped=True,
            hold=True,
            reason=HOLD_UNSUPPORTED,
        )
    if footer_already_present(blob, "telegram_ru"):
        return FooterResult(
            channel="telegram_ru",
            applied=False,
            skipped=True,
            hold=False,
            reason="footer already present",
            rich_block=telegram_ru_rich_footer_block(),
            text_html=TG_RU_FOOTER_HTML,
            text_plain=TG_RU_FOOTER_PLAIN,
        )
    blocks.append(telegram_ru_rich_footer_block())
    return FooterResult(
        channel="telegram_ru",
        applied=True,
        skipped=False,
        hold=False,
        reason="injected",
        rich_block=telegram_ru_rich_footer_block(),
        text_html=TG_RU_FOOTER_HTML,
        text_plain=TG_RU_FOOTER_PLAIN,
    )


def inject_plain_text(
    text: str | None,
    *,
    market: str,
    html: bool = False,
    max_chars: int | None = None,
) -> tuple[str, FooterResult]:
    """Append footer to a Telegram sendMessage / caption body."""
    body = text or ""
    if market != "ru":
        if ru_cross_promo_in_en(body):
            return body, FooterResult(
                channel="telegram_en",
                applied=False,
                skipped=True,
                hold=True,
                reason="EN payload contains RU cross-promo footer",
            )
        return body, FooterResult(
            channel="telegram_en",
            applied=False,
            skipped=True,
            hold=False,
            reason="EN has no RU footer",
        )
    if contains_forbidden_max_url(body):
        return body, FooterResult(
            channel="telegram_ru",
            applied=False,
            skipped=True,
            hold=True,
            reason="legacy MAX URL in payload",
        )
    snippet = TG_RU_FOOTER_HTML if html else TG_RU_FOOTER_PLAIN
    if footer_already_present(body, "telegram_ru"):
        return body, FooterResult(
            channel="telegram_ru",
            applied=False,
            skipped=True,
            hold=False,
            reason="footer already present",
            text_html=TG_RU_FOOTER_HTML,
            text_plain=TG_RU_FOOTER_PLAIN,
        )
    glued = f"{body.rstrip()}\n\n{snippet}" if body.strip() else snippet
    if max_chars is not None and len(glued) > max_chars:
        keep = max_chars - len(snippet) - 2
        if keep < 80:
            return body, FooterResult(
                channel="telegram_ru",
                applied=False,
                skipped=True,
                hold=True,
                reason=HOLD_UNSUPPORTED,
            )
        glued = f"{body[:keep].rstrip()}\n\n{snippet}"
    return glued, FooterResult(
        channel="telegram_ru",
        applied=True,
        skipped=False,
        hold=False,
        reason="injected",
        text_html=TG_RU_FOOTER_HTML,
        text_plain=TG_RU_FOOTER_PLAIN,
    )


def inject_max_html(text: str, *, max_chars: int = 4000) -> tuple[str, FooterResult]:
    """Append MAX → Telegram RU footer; never byte-truncate the footer itself."""
    if contains_forbidden_max_url(text):
        return text, FooterResult(
            channel="max_ru",
            applied=False,
            skipped=True,
            hold=True,
            reason="legacy MAX URL in payload",
        )
    snippet = f"<p>{MAX_FOOTER_HTML}</p>"
    if footer_already_present(text, "max_ru"):
        return text, FooterResult(
            channel="max_ru",
            applied=False,
            skipped=True,
            hold=False,
            reason="footer already present",
            text_html=MAX_FOOTER_HTML,
            text_plain=MAX_FOOTER_PLAIN,
        )
    glued = f"{text.rstrip()}\n{snippet}" if text.strip() else snippet
    if len(glued) > max_chars:
        keep = max_chars - len(snippet) - 1
        if keep < 120:
            return text, FooterResult(
                channel="max_ru",
                applied=False,
                skipped=True,
                hold=True,
                reason=HOLD_UNSUPPORTED,
            )
        # Semantic cut: prefer paragraph boundary over mid-word truncation.
        cut = text[:keep]
        for sep in ("</p>", "</h2>", "\n"):
            idx = cut.rfind(sep)
            if idx >= 80:
                cut = cut[: idx + len(sep)]
                break
        glued = f"{cut.rstrip()}\n{snippet}"
    return glued, FooterResult(
        channel="max_ru",
        applied=True,
        skipped=False,
        hold=False,
        reason="injected",
        text_html=MAX_FOOTER_HTML,
        text_plain=MAX_FOOTER_PLAIN,
    )


__all__ = [
    "FORBIDDEN_MAX_URL_MARKERS",
    "HOLD_UNSUPPORTED",
    "MAX_FOOTER_HTML",
    "MAX_FOOTER_PLAIN",
    "MAX_PUBLIC_URL",
    "TELEGRAM_RU_URL",
    "TG_RU_FOOTER_HTML",
    "TG_RU_FOOTER_PLAIN",
    "FooterResult",
    "contains_forbidden_max_url",
    "footer_already_present",
    "inject_max_html",
    "inject_plain_text",
    "inject_telegram_rich",
    "ru_cross_promo_in_en",
    "telegram_ru_rich_footer_block",
]
