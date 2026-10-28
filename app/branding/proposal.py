"""Draft channel packaging from Editorial Engine v2.2 §0.1.

Username / URLs are immutable. Apply only after human approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import Market

CHANNEL_BRANDING_VERSION = "v2.2-draft-2026-10-28"

TELEGRAM_CHAT_LIMITS = {
    "title": 128,
    "description": 255,
}


@dataclass(frozen=True, slots=True)
class ChannelBrandingDraft:
    market: Market
    username: str
    url: str
    title: str
    description: str
    website_url: str
    pinned_welcome_text: str
    title_action: Literal["keep", "rename"]
    notes: str = ""


_RU = ChannelBrandingDraft(
    market="ru",
    username="@wegotrip_ru",
    url="https://t.me/wegotrip_ru",
    title="WeGoTrip — Куда сходить и что посмотреть",
    description=(
        "Куда сходить в выходные и куда поехать дальше? Музеи, выставки, необычные "
        "места, маршруты и новости для местных и путешественников. Пишем по делу, "
        "с любопытством и иногда с улыбкой. https://wegotrip.ru"
    ),
    website_url="https://wegotrip.ru",
    pinned_welcome_text=(
        "Привет! Это WeGoTrip 👋\n\n"
        "Здесь ищем ответы на два вечных вопроса: куда выбраться в выходные и что "
        "посмотреть, когда уже выбрались. Подсказываем интересные музеи, выставки, "
        "прогулки и необычные места, рассказываем истории городов и делимся новостями, "
        "которые действительно пригодятся в поездке.\n\n"
        "Иногда советуем аудиогиды и экскурсии WeGoTrip — когда они к месту. Иногда "
        "просто рассказываем что-то классное.\n\n"
        "Если у вас пока нет планов на выходные, считайте, что теперь есть с чего начать.\n\n"
        "English channel: @wegotrip"
    ),
    title_action="keep",
    notes="RU title is already good; only description (+ .ru site) should change.",
)

_EN = ChannelBrandingDraft(
    market="en",
    username="@wegotrip",
    url="https://t.me/wegotrip",
    title="WeGoTrip — Things to Do & Travel Ideas",
    description=(
        "Good ideas for this weekend and your next trip. Museums, exhibitions, "
        "surprising places, city routes and travel updates for locals and travelers. "
        "Useful, curious, occasionally witty. https://wegotrip.com"
    ),
    website_url="https://wegotrip.com",
    pinned_welcome_text=(
        "Hi, we're WeGoTrip 👋\n\n"
        "For the weekends when you want to get out, and the trips when you want to see "
        "more than the usual checklist. Expect clever city ideas, exhibitions, museums, "
        "unusual places, useful travel updates and the odd story worth sharing.\n\n"
        "Sometimes there's a WeGoTrip audio tour that fits perfectly. Sometimes a good "
        "idea is all you need.\n\n"
        "Your next plan might be one post away.\n\n"
        "По-русски: @wegotrip_ru"
    ),
    title_action="rename",
    notes="Rename away from commercial 'Tickets'; keep @wegotrip username.",
)


def proposed_branding_for(market: Market) -> ChannelBrandingDraft:
    return _RU if market == "ru" else _EN


def validate_branding_lengths(draft: ChannelBrandingDraft) -> list[str]:
    """Return human-readable errors if Bot API limits are exceeded."""
    errors: list[str] = []
    if len(draft.title) > TELEGRAM_CHAT_LIMITS["title"]:
        errors.append(f"{draft.market} title {len(draft.title)} > {TELEGRAM_CHAT_LIMITS['title']}")
    if len(draft.description) > TELEGRAM_CHAT_LIMITS["description"]:
        errors.append(
            f"{draft.market} description {len(draft.description)} > "
            f"{TELEGRAM_CHAT_LIMITS['description']}"
        )
    return errors


__all__ = [
    "CHANNEL_BRANDING_VERSION",
    "TELEGRAM_CHAT_LIMITS",
    "ChannelBrandingDraft",
    "proposed_branding_for",
    "validate_branding_lengths",
]
