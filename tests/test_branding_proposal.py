"""Channel branding drafts stay within Telegram Bot API limits and preserve usernames."""

from __future__ import annotations

from app.branding.proposal import (
    CHANNEL_BRANDING_VERSION,
    proposed_branding_for,
    validate_branding_lengths,
)


def test_proposed_branding_lengths_and_usernames():
    ru = proposed_branding_for("ru")
    en = proposed_branding_for("en")
    assert ru.username == "@wegotrip_ru"
    assert en.username == "@wegotrip"
    assert ru.url == "https://t.me/wegotrip_ru"
    assert en.url == "https://t.me/wegotrip"
    assert ru.title_action == "keep"
    assert en.title_action == "rename"
    assert "wegotrip.ru" in ru.description
    assert "wegotrip.com" in en.description
    assert "Tickets" not in en.title
    assert validate_branding_lengths(ru) == []
    assert validate_branding_lengths(en) == []
    assert CHANNEL_BRANDING_VERSION.startswith("v2.2")
