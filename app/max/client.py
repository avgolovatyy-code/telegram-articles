"""Max Bot API client (platform-api2.max.ru)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.catalog.http import RateLimiter, request_with_retries
from app.config import Settings, get_settings
from app.errors import ConfigurationError, MaxError, MaxRateLimited, MaxValidationError
from app.logging_setup import get_logger
from app.max.chat_id import resolve_max_chat_id

log = get_logger("max.api")

#: Max allows at most two messages per second per chat; stay well under it.
CHANNEL_RATE_LIMIT_RPS = 0.5

DEFAULT_CA_PATH = Path(__file__).resolve().parent / "certs" / "russian_trusted_root_ca.crt"


@dataclass(slots=True)
class SentMaxMessage:
    message_id: str | None
    chat_id: int
    raw: dict[str, Any]


def _ssl_verify(settings: Settings) -> bool | str:
    """TLS verify setting for httpx.

    Max's ``platform-api2.max.ru`` is often served with the Russian trusted root
    (Минцифры). Prefer an explicit CA file, then the bundled PEM, else system CAs.
    """
    if not settings.max_ssl_verify:
        return False
    candidates = [
        settings.max_ssl_ca_file,
        str(DEFAULT_CA_PATH),
        # Source-tree path when the console script loads a site-packages install
        # that was built without package data (older images).
        "/app/app/max/certs/russian_trusted_root_ca.crt",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    log.warning(
        "max.ssl_ca_missing",
        default=str(DEFAULT_CA_PATH),
        hint="package data *.crt missing from install; falling back to system CAs",
    )
    return True


class MaxBotClient:
    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.max_bot_token:
            raise ConfigurationError("MAX_BOT_TOKEN is not set")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(self.settings.max_timeout_seconds),
            base_url=self.settings.max_api_base_url.rstrip("/"),
            headers={"Authorization": self.settings.max_bot_token},
            verify=_ssl_verify(self.settings),
        )
        self._limiter = RateLimiter(CHANNEL_RATE_LIMIT_RPS)
        self._resolved_chat_id: int | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def ru_chat_id(self) -> int:
        if self._resolved_chat_id is not None:
            return self._resolved_chat_id
        raw = self.settings.max_ru_channel_id
        if not raw:
            raise ConfigurationError("MAX_RU_CHANNEL_ID is not set")
        self._resolved_chat_id = resolve_max_chat_id(
            raw, timeout=self.settings.max_timeout_seconds
        )
        return self._resolved_chat_id

    def call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = request_with_retries(
            self._client,
            method,
            path,
            params=params,
            json=json_body,
            max_retries=self.settings.max_max_retries,
            limiter=self._limiter,
            error_cls=MaxError,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise MaxError(f"{path}: non-JSON response") from exc

        if response.status_code == 429:
            raise MaxRateLimited(str(data.get("message") or data), retry_after=1)
        if response.status_code in {400, 403, 404}:
            code = data.get("code") or response.status_code
            message = data.get("message") or data
            raise MaxValidationError(
                f"{path}: {code}: {message}",
                status_code=response.status_code,
                payload=data,
            )
        if response.status_code >= 400:
            raise MaxError(
                f"{path}: HTTP {response.status_code}: {data}",
                status_code=response.status_code,
                payload=data,
            )
        return data if isinstance(data, dict) else {"result": data}

    def get_me(self) -> dict[str, Any]:
        return self.call("GET", "/me")

    def get_chat(self, chat_id: int | None = None) -> dict[str, Any]:
        cid = self.ru_chat_id() if chat_id is None else int(chat_id)
        return self.call("GET", f"/chats/{cid}")

    def send_message(
        self,
        *,
        chat_id: int | None = None,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        format: str | None = "markdown",
        notify: bool = True,
        disable_link_preview: bool = False,
    ) -> SentMaxMessage:
        cid = self.ru_chat_id() if chat_id is None else int(chat_id)
        body: dict[str, Any] = {"text": text, "notify": notify}
        if format:
            body["format"] = format
        if attachments is not None:
            body["attachments"] = attachments
        params: dict[str, Any] = {"chat_id": cid}
        if disable_link_preview:
            params["disable_link_preview"] = "true"
        data = self.call("POST", "/messages", params=params, json_body=body)
        message = data.get("message") if isinstance(data, dict) else None
        message = message if isinstance(message, dict) else {}
        mid = None
        body_obj = message.get("body") if isinstance(message.get("body"), dict) else {}
        if isinstance(body_obj, dict):
            mid = body_obj.get("mid")
        return SentMaxMessage(message_id=str(mid) if mid else None, chat_id=cid, raw=data)


def build_max_client(settings: Settings | None = None) -> MaxBotClient | None:
    """Return a Max client when RU Max publishing is configured; otherwise ``None``."""
    settings = settings or get_settings()
    if not settings.max_ru_active:
        return None
    return MaxBotClient(settings)


__all__ = [
    "CHANNEL_RATE_LIMIT_RPS",
    "DEFAULT_CA_PATH",
    "MaxBotClient",
    "SentMaxMessage",
    "build_max_client",
]
