"""Slack Web API client.

Only the three methods the engine needs: post a message, update one in place and
answer an interaction through its ``response_url``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.catalog.http import request_with_retries
from app.config import Settings, get_settings
from app.errors import ConfigurationError, UpstreamError
from app.logging_setup import get_logger

log = get_logger("slack.client")

SLACK_API_BASE = "https://slack.com/api"


class SlackError(UpstreamError):
    """Slack rejected the call."""


@dataclass(slots=True)
class SlackMessage:
    channel: str
    ts: str
    raw: dict[str, Any]


class SlackClient:
    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.slack_bot_token:
            raise ConfigurationError("SLACK_BOT_TOKEN is not set")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=SLACK_API_BASE,
            timeout=httpx.Timeout(20.0),
            headers={
                "Authorization": f"Bearer {self.settings.slack_bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = request_with_retries(
            self._client, "POST", f"/{method}", json=payload, max_retries=2, error_cls=SlackError
        )
        body = response.json()
        if not body.get("ok"):
            raise SlackError(f"{method}: {body.get('error', 'unknown error')}", payload=body)
        return body

    def post_message(
        self, *, blocks: list[dict[str, Any]], text: str, channel: str | None = None
    ) -> SlackMessage:
        target = channel or self.settings.slack_channel
        if not target:
            raise ConfigurationError("SLACK_CHANNEL is not set")
        body = self._call(
            "chat.postMessage",
            {"channel": target, "blocks": blocks, "text": text, "unfurl_links": False},
        )
        return SlackMessage(channel=body.get("channel", target), ts=body.get("ts", ""), raw=body)

    def update_message(
        self, *, channel: str, ts: str, blocks: list[dict[str, Any]], text: str
    ) -> None:
        self._call("chat.update", {"channel": channel, "ts": ts, "blocks": blocks, "text": text})

    def respond(self, response_url: str, payload: dict[str, Any]) -> None:
        """Reply to an interaction. ``response_url`` is pre-authorised by Slack."""
        try:
            httpx.post(response_url, json=payload, timeout=10.0)
        except httpx.HTTPError as exc:
            log.warning("slack.respond_failed", error=str(exc))


class NullSlackClient:
    """Used when Slack is not configured: records calls, sends nothing."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.sent: list[tuple[str, str]] = []

    def close(self) -> None:
        return None

    def post_message(
        self, *, blocks: list[dict[str, Any]], text: str, channel: str | None = None
    ) -> SlackMessage:
        _ = blocks
        self.sent.append((channel or "-", text))
        return SlackMessage(channel=channel or "-", ts="0.0", raw={"ok": True, "dry_run": True})

    def update_message(
        self, *, channel: str, ts: str, blocks: list[dict[str, Any]], text: str
    ) -> None:
        _ = (channel, ts, blocks)
        self.sent.append(("update", text))

    def respond(self, response_url: str, payload: dict[str, Any]) -> None:
        _ = (response_url, payload)


def build_slack_client(settings: Settings | None = None):
    settings = settings or get_settings()
    if not settings.slack_enabled or not settings.slack_bot_token:
        return NullSlackClient(settings)
    return SlackClient(settings)


__all__ = [
    "SLACK_API_BASE",
    "NullSlackClient",
    "SlackClient",
    "SlackError",
    "SlackMessage",
    "build_slack_client",
]
