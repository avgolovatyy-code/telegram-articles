"""Resolve Max channel identifiers.

Public links look like ``https://max.ru/idNNNNNNNN_biz``. That slug is **not**
the Bot API ``chat_id``. Max only documents ``chat_id`` from events
(``bot_added`` / subscriptions), but the public channel page also embeds
``channelId:<positive>``, and the API chat id is the negated value
(``-<channelId>``).
"""

from __future__ import annotations

import re
from functools import lru_cache

import httpx

from app.errors import ConfigurationError, MaxError

_CHANNEL_ID_RE = re.compile(r"channelId\s*:\s*(\d+)")
_NUMERIC_RE = re.compile(r"^-?\d+$")


def normalize_channel_ref(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise ConfigurationError("MAX_RU_CHANNEL_ID is empty")
    value = value.removeprefix("https://").removeprefix("http://")
    value = value.removeprefix("max.ru/").removeprefix("web.max.ru/")
    value = value.split("?", 1)[0].split("#", 1)[0].strip("/")
    return value


def parse_numeric_chat_id(raw: str) -> int | None:
    ref = normalize_channel_ref(raw)
    if _NUMERIC_RE.fullmatch(ref):
        return int(ref)
    return None


def chat_id_from_public_html(html: str) -> int:
    match = _CHANNEL_ID_RE.search(html)
    if match is None:
        raise MaxError("Max public page did not contain channelId")
    return -int(match.group(1))


@lru_cache(maxsize=32)
def resolve_chat_id_from_slug(slug: str, *, timeout: float = 20.0) -> int:
    """Fetch ``https://max.ru/<slug>`` and return the API ``chat_id``."""
    ref = normalize_channel_ref(slug)
    if not ref.startswith("id"):
        ref = f"id{ref}"
    url = f"https://max.ru/{ref}"
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "WeGoTripContentEngine/1.0"},
        )
    except httpx.HTTPError as exc:
        raise MaxError(f"failed to resolve Max channel slug via {url}: {exc}") from exc
    if response.status_code >= 400:
        raise MaxError(
            f"failed to resolve Max channel slug via {url}: HTTP {response.status_code}"
        )
    return chat_id_from_public_html(response.text)


def resolve_max_chat_id(raw: str, *, timeout: float = 20.0) -> int:
    """Accept a numeric chat id or a public Max channel slug / URL."""
    numeric = parse_numeric_chat_id(raw)
    if numeric is not None:
        return numeric
    return resolve_chat_id_from_slug(raw, timeout=timeout)


__all__ = [
    "chat_id_from_public_html",
    "normalize_channel_ref",
    "parse_numeric_chat_id",
    "resolve_chat_id_from_slug",
    "resolve_max_chat_id",
]
