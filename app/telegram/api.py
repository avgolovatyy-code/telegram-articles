"""Telegram Bot API client (official API only, no userbots)."""

from __future__ import annotations

import json
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
        if self.chat_username:
            return f"https://t.me/{self.chat_username.lstrip('@')}/{self.message_id}"
        return None


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
        return {"id": chat_id, "username": str(chat_id).lstrip("@"), "type": "channel"}

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


def _to_sent_message(result: dict[str, Any], chat_id: str) -> SentMessage:
    chat = result.get("chat") or {}
    return SentMessage(
        message_id=int(result.get("message_id", 0)),
        chat_id=str(chat.get("id", chat_id)),
        chat_username=chat.get("username")
        or (str(chat_id).lstrip("@") if str(chat_id).startswith("@") else None),
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
]
