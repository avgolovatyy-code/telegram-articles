"""Brand Max bot + RU channel to match Telegram @wegotrip_ru.

Max is a forward-only mirror of new Telegram RU production posts — there is no
catch-up of historical articles. Branding is applied via the Max Bot API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.logging_setup import get_logger
from app.max.client import MaxBotClient

log = get_logger("max.branding")

#: Mirror of the live Telegram RU channel (@wegotrip_ru) title/description,
#: adapted for Max (bot deep-link instead of wegotrip.com-only footer).
CHANNEL_TITLE = "WeGoTrip — Куда сходить и что посмотреть"
CHANNEL_DESCRIPTION = (
    "Живые гиды по городам и практичные подборки — интересно читать, полезно перед поездкой.\n"
    "Аудиогиды и билеты в музеи по всему миру — с приоритетом городов России.\n"
    "https://wegotrip.ru/"
)

#: Align with Telegram bot display name (wegotripbot → "WeGoTrip Tours & Tickets").
BOT_NAME = "WeGoTrip Tours & Tickets"
BOT_DESCRIPTION = (
    "Аудиогиды и билеты в музеи и на достопримечательности. "
    "Читайте подборки в канале WeGoTrip и бронируйте в приложении.\n"
    "https://wegotrip.ru/"
)

BOT_COMMANDS = [
    {"name": "start", "description": "О боте и канале WeGoTrip"},
    {"name": "help", "description": "Как пользоваться ботом"},
]


@dataclass(slots=True)
class BrandingResult:
    bot: dict[str, Any]
    chat: dict[str, Any]
    pinned: bool


def apply_max_branding(
    settings: Settings | None = None,
    *,
    client: MaxBotClient | None = None,
    pin_intro: bool = True,
) -> BrandingResult:
    """Update Max bot profile + RU channel chrome to match Telegram RU."""
    settings = settings or get_settings()
    owns = client is None
    client = client or MaxBotClient(settings)
    try:
        bot_payload: dict[str, Any] = {
            "first_name": BOT_NAME[:64],
            "description": BOT_DESCRIPTION,
        }
        try:
            bot = client.call("PATCH", "/me", json_body=bot_payload)
        except Exception:
            # Some Max deployments accept ``name`` instead of ``first_name``.
            bot = client.call(
                "PATCH",
                "/me",
                json_body={"name": BOT_NAME[:64], "description": BOT_DESCRIPTION},
            )
        try:
            client.call("PATCH", "/me/commands", json_body={"commands": BOT_COMMANDS})
        except Exception as exc:  # noqa: BLE001 — commands are optional chrome
            log.warning("max.branding_commands_failed", error=str(exc))

        chat_id = client.ru_chat_id()
        me = client.get_me()
        bot_username = me.get("username") or ""
        description = CHANNEL_DESCRIPTION
        if bot_username:
            description = f"{description}\nБот: https://max.ru/{bot_username}"

        chat = client.call(
            "PATCH",
            f"/chats/{chat_id}",
            json_body={
                "title": CHANNEL_TITLE[:200],
                "description": description,
                "notify": False,
            },
        )

        pinned = False
        if pin_intro:
            pinned = _ensure_intro_pin(client, chat_id)

        log.info(
            "max.branding_applied",
            bot_name=BOT_NAME,
            chat_id=chat_id,
            pinned=pinned,
        )
        return BrandingResult(bot=bot if isinstance(bot, dict) else {}, chat=chat, pinned=pinned)
    finally:
        if owns:
            client.close()


def _ensure_intro_pin(client: MaxBotClient, chat_id: int) -> bool:
    intro = (
        f"**{CHANNEL_TITLE}**\n\n"
        "Здесь — живые гиды по городам и практичные подборки: куда сходить, "
        "что посмотреть и какие билеты взять.\n\n"
        "Россия — в приоритете; дальше — другие страны.\n"
        "Аудиогиды и билеты: https://wegotrip.ru/"
    )
    try:
        sent = client.send_message(chat_id=chat_id, text=intro, format="markdown")
        mid = sent.message_id
        if not mid:
            return False
        client.call(
            "PUT",
            f"/chats/{chat_id}/pin",
            json_body={"message_id": mid, "notify": False},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("max.branding_pin_failed", error=str(exc))
        return False


__all__ = [
    "BOT_COMMANDS",
    "BOT_DESCRIPTION",
    "BOT_NAME",
    "CHANNEL_DESCRIPTION",
    "CHANNEL_TITLE",
    "BrandingResult",
    "apply_max_branding",
]
