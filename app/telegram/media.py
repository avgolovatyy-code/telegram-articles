"""Media validation before publication (spec §30)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.config import Settings, get_settings
from app.logging_setup import get_logger

log = get_logger("telegram.media")

TELEGRAM_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
TELEGRAM_AUDIO_TYPES = {"audio/mpeg", "audio/mp4", "audio/ogg", "audio/aac", "audio/x-m4a"}

#: Telegram's own limit for photos sent by URL.
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 50 * 1024 * 1024

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".oga", ".aac")


@dataclass(slots=True)
class MediaCheck:
    url: str
    ok: bool
    kind: str = "photo"
    content_type: str | None = None
    content_length: int | None = None
    error: str | None = None
    fingerprint: str | None = None


class MediaValidator:
    """Checks reachability, type and size, and rejects duplicates within one article."""

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=15.0, follow_redirects=True)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def check(self, url: str, *, kind: str = "photo") -> MediaCheck:
        if not url or not url.startswith("https://"):
            return MediaCheck(url, False, kind, error="media URL must be absolute https")

        path = urlsplit(url).path.lower()
        expected = _IMAGE_EXTENSIONS if kind == "photo" else _AUDIO_EXTENSIONS
        extension_ok = path.endswith(expected)

        if not self.settings.validate_media_over_network:
            return MediaCheck(
                url,
                extension_ok,
                kind,
                error=None if extension_ok else f"unsupported extension for {kind}",
                fingerprint=_fingerprint(url),
            )

        try:
            response = self._get_client().head(url)
            if response.status_code >= 400 or "content-type" not in response.headers:
                response = self._get_client().get(url, headers={"Range": "bytes=0-1024"})
        except httpx.HTTPError as exc:
            return MediaCheck(url, False, kind, error=f"unreachable: {exc}")

        if response.status_code >= 400:
            return MediaCheck(url, False, kind, error=f"HTTP {response.status_code}")

        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        length_header = response.headers.get("content-range") or response.headers.get(
            "content-length"
        )
        content_length = _parse_length(length_header)

        allowed = TELEGRAM_PHOTO_TYPES if kind == "photo" else TELEGRAM_AUDIO_TYPES
        if content_type and content_type not in allowed:
            return MediaCheck(
                url, False, kind, content_type, content_length, f"unsupported type {content_type}"
            )
        if not content_type and not extension_ok:
            return MediaCheck(url, False, kind, error="unknown media type")

        limit = MAX_PHOTO_BYTES if kind == "photo" else MAX_AUDIO_BYTES
        limit = min(limit, self.settings.media_max_bytes) if kind == "photo" else limit
        if content_length and content_length > limit:
            return MediaCheck(
                url, False, kind, content_type, content_length, f"file too large: {content_length}"
            )

        return MediaCheck(
            url, True, kind, content_type, content_length, fingerprint=_fingerprint(url)
        )

    def check_many(self, urls: list[tuple[str, str]]) -> list[MediaCheck]:
        """Validate ``(url, kind)`` pairs and drop duplicates."""
        results: list[MediaCheck] = []
        seen: set[str] = set()
        for url, kind in urls:
            check = self.check(url, kind=kind)
            fingerprint = check.fingerprint
            if check.ok and fingerprint:
                if fingerprint in seen:
                    check = MediaCheck(url, False, kind, error="duplicate image in article")
                else:
                    seen.add(fingerprint)
            results.append(check)
        return results


def _parse_length(header: str | None) -> int | None:
    if not header:
        return None
    if "/" in header:
        header = header.rsplit("/", 1)[-1]
    try:
        return int(header)
    except ValueError:
        return None


def _fingerprint(url: str) -> str:
    """Media URLs contain a content hash, so the path is a good duplicate key."""
    path = urlsplit(url).path
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:24]


__all__ = [
    "MAX_AUDIO_BYTES",
    "MAX_PHOTO_BYTES",
    "TELEGRAM_AUDIO_TYPES",
    "TELEGRAM_PHOTO_TYPES",
    "MediaCheck",
    "MediaValidator",
]
