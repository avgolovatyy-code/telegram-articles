"""Telegram Bot API client (official API only, no userbots)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.catalog.http import RateLimiter, request_with_retries
from app.config import Settings, get_settings
from app.errors import (
    ConfigurationError,
    TelegramError,
    TelegramRateLimited,
    TelegramValidationError,
)
from app.logging_setup import get_logger

log = get_logger("telegram.api")

#: Telegram allows ~20 messages per minute to the same channel; stay well under it.
CHANNEL_RATE_LIMIT_RPS = 0.25


@dataclass(slots=True)
class SentMessage:
    message_id: int
    chat_id: str
    chat_username: str | None
    raw: dict[str, Any]

    @property
    def url(self) -> str | None:
        return message_url(self.chat_id, self.chat_username, self.message_id)


class TelegramBotClient:
    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.telegram_bot_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is not set")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(self.settings.telegram_timeout_seconds),
            base_url=(
                f"{self.settings.telegram_api_base_url.rstrip('/')}"
                f"/bot{self.settings.telegram_bot_token}"
            ),
        )
        self._limiter = RateLimiter(CHANNEL_RATE_LIMIT_RPS)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------ core
    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {key: value for key, value in payload.items() if value is not None}
        encoded = {
            key: (
                json.dumps(value, ensure_ascii=False) if isinstance(value, dict | list) else value
            )
            for key, value in body.items()
        }
        response = request_with_retries(
            self._client,
            "POST",
            f"/{method}",
            data=encoded,
            max_retries=self.settings.telegram_max_retries,
            limiter=self._limiter,
            error_cls=TelegramError,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramError(f"{method}: non-JSON response") from exc

        if data.get("ok"):
            return data.get("result", {})

        description = str(data.get("description", "unknown error"))
        parameters = data.get("parameters") or {}
        if response.status_code == 429 or "Too Many Requests" in description:
            raise TelegramRateLimited(description, int(parameters.get("retry_after", 30)))
        if response.status_code in {400, 403}:
            raise TelegramValidationError(
                f"{method}: {description}", status_code=response.status_code, payload=data
            )
        raise TelegramError(f"{method}: {description}", status_code=response.status_code)

    # --------------------------------------------------------------- methods
    def get_me(self) -> dict[str, Any]:
        return self.call("getMe", {})

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        return self.call("getChat", {"chat_id": chat_id})

    def send_rich_message(
        self,
        chat_id: str,
        rich_message: dict[str, Any],
        *,
        disable_notification: bool = False,
        protect_content: bool = False,
    ) -> SentMessage:
        result = self.call(
            "sendRichMessage",
            {
                "chat_id": chat_id,
                "rich_message": rich_message,
                "disable_notification": disable_notification,
                "protect_content": protect_content,
            },
        )
        return _to_sent_message(result, chat_id)

    def edit_rich_message(
        self, chat_id: str, message_id: int, rich_message: dict[str, Any]
    ) -> dict[str, Any]:
        return self.call(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "rich_message": rich_message},
        )

    def send_message(self, chat_id: str, text: str) -> SentMessage:
        result = self.call("sendMessage", {"chat_id": chat_id, "text": text})
        return _to_sent_message(result, chat_id)

    def get_updates(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Recent updates — used to discover the id of a private channel."""
        result = self.call(
            "getUpdates",
            {"limit": limit, "allowed_updates": ["channel_post", "my_chat_member", "message"]},
        )
        return result if isinstance(result, list) else []

    def discover_chats(self) -> list[dict[str, Any]]:
        """Chats the bot has seen, with the ids to put into configuration.

        A private channel has no ``@username``, so its numeric ``-100…`` id is the only
        way to address it. Telegram only reveals that id once the bot has seen an event
        in the channel, which happens as soon as it is added as an administrator.
        """
        seen: dict[str, dict[str, Any]] = {}
        for update in self.get_updates():
            for key in ("channel_post", "message", "my_chat_member"):
                payload = update.get(key)
                if not isinstance(payload, dict):
                    continue
                chat = payload.get("chat")
                if not isinstance(chat, dict) or "id" not in chat:
                    continue
                seen[str(chat["id"])] = {
                    "id": str(chat["id"]),
                    "type": chat.get("type"),
                    "title": chat.get("title"),
                    "username": chat.get("username"),
                }
        return list(seen.values())


class DryRunTelegramClient:
    """Builds and validates payloads but never contacts Telegram."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self._counter = 1000

    def close(self) -> None:
        return None

    def get_me(self) -> dict[str, Any]:
        return {"id": 0, "username": "dry_run_bot", "is_bot": True}

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        username = None if is_numeric_chat_id(chat_id) else str(chat_id).lstrip("@")
        return {"id": chat_id, "username": username, "type": "channel"}

    def send_rich_message(
        self,
        chat_id: str,
        rich_message: dict[str, Any],
        *,
        disable_notification: bool = False,
        protect_content: bool = False,
    ) -> SentMessage:
        self._counter += 1
        self.sent.append((chat_id, rich_message))
        log.info("telegram.dry_run_send", chat_id=chat_id, message_id=self._counter)
        return SentMessage(
            message_id=self._counter,
            chat_id=str(chat_id),
            chat_username=str(chat_id).lstrip("@"),
            raw={"dry_run": True},
        )

    def edit_rich_message(
        self, chat_id: str, message_id: int, rich_message: dict[str, Any]
    ) -> dict[str, Any]:
        self.sent.append((chat_id, rich_message))
        return {"dry_run": True, "message_id": message_id}

    def send_message(self, chat_id: str, text: str) -> SentMessage:
        self._counter += 1
        return SentMessage(self._counter, str(chat_id), str(chat_id).lstrip("@"), {"text": text})

    def get_updates(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return []

    def discover_chats(self) -> list[dict[str, Any]]:
        return []


def is_numeric_chat_id(value: str) -> bool:
    """Private channels have no @username and are addressed by a ``-100…`` id."""
    return bool(re.fullmatch(r"-?\d+", str(value).strip()))


def message_url(chat_id: str, chat_username: str | None, message_id: int) -> str | None:
    """Public link for a sent message, or the internal ``t.me/c/…`` form.

    Private channels are reachable only as ``https://t.me/c/<id without -100>/<msg>``,
    and that link works for members of the channel.
    """
    if chat_username:
        return f"https://t.me/{chat_username.lstrip('@')}/{message_id}"
    raw = str(chat_id)
    if is_numeric_chat_id(raw) and raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{message_id}"
    return None


def _to_sent_message(result: dict[str, Any], chat_id: str) -> SentMessage:
    chat = result.get("chat") or {}
    resolved_id = str(chat.get("id", chat_id))
    username = chat.get("username")
    if not username and str(chat_id).startswith("@"):
        username = str(chat_id).lstrip("@")
    return SentMessage(
        message_id=int(result.get("message_id", 0)),
        chat_id=resolved_id,
        chat_username=username,
        raw=result,
    )


def build_telegram_client(settings: Settings | None = None):
    settings = settings or get_settings()
    if settings.telegram_dry_run or not settings.telegram_bot_token:
        return DryRunTelegramClient(settings)
    return TelegramBotClient(settings)


__all__ = [
    "CHANNEL_RATE_LIMIT_RPS",
    "DryRunTelegramClient",
    "SentMessage",
    "TelegramBotClient",
    "build_telegram_client",
    "is_numeric_chat_id",
    "message_url",
]
