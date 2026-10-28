"""Resolve Max channel identifiers.

Public links look like ``https://max.ru/channel_wegotrip`` or legacy
``https://max.ru/idNNNNNNNN_biz``. Those slugs are **not** the Bot API
``chat_id``. The public channel page embeds ``channelId:<positive>``, and the
API chat id is the negated value (``-<channelId>``).

Canonical public URL (v1.1): ``https://max.ru/channel_wegotrip``.
Never recreate the channel or replace a known numeric ``MAX_RU_CHANNEL_ID``.
"""

from __future__ import annotations

import re
from functools import lru_cache

import httpx

from app.errors import ConfigurationError, MaxError

_CHANNEL_ID_RE = re.compile(r"channelId\s*:\s*(\d+)")
_NUMERIC_RE = re.compile(r"^-?\d+$")

#: Canonical public address for the existing WeGoTrip Max channel.
CANONICAL_PUBLIC_URL = "https://max.ru/channel_wegotrip"
CANONICAL_PUBLIC_SLUG = "channel_wegotrip"


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


def public_page_url(slug_or_url: str) -> str:
    """Build ``https://max.ru/<slug>`` for any public slug (channel_* or id*)."""
    ref = normalize_channel_ref(slug_or_url)
    return f"https://max.ru/{ref}"


@lru_cache(maxsize=32)
def resolve_chat_id_from_slug(slug: str, *, timeout: float = 20.0) -> int:
    """Fetch the public Max page and return the API ``chat_id``.

    Accepts ``channel_wegotrip``, ``id…_biz``, or full ``https://max.ru/…`` URLs.
    Does **not** invent a new channel — only resolves an existing public page.
    """
    url = public_page_url(slug)
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
        raise MaxError(f"failed to resolve Max channel slug via {url}: HTTP {response.status_code}")
    return chat_id_from_public_html(response.text)


def resolve_max_chat_id(raw: str, *, timeout: float = 20.0) -> int:
    """Accept a numeric chat id or a public Max channel slug / URL.

    Prefer keeping a numeric ``MAX_RU_CHANNEL_ID`` in production so public URL
    renames never change the API destination.
    """
    numeric = parse_numeric_chat_id(raw)
    if numeric is not None:
        return numeric
    return resolve_chat_id_from_slug(raw, timeout=timeout)


__all__ = [
    "CANONICAL_PUBLIC_SLUG",
    "CANONICAL_PUBLIC_URL",
    "chat_id_from_public_html",
    "normalize_channel_ref",
    "parse_numeric_chat_id",
    "public_page_url",
    "resolve_chat_id_from_slug",
    "resolve_max_chat_id",
]
