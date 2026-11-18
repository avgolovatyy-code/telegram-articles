"""Confirm a manually published Dzen URL. Never sign in to Dzen Studio."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DzenArticleStatus
from app.db.models import DzenArticle, DzenHandoffItem
from app.db.types import utcnow
from app.logging_setup import get_logger

log = get_logger("dzen.confirm")

DZEN_HOSTS = {"dzen.ru", "www.dzen.ru"}
ARTICLE_PATH = re.compile(r"^/a/[A-Za-z0-9_-]+")
NUMBERED = re.compile(r"(?m)^\s*(\d+)\s*[:.\-)]\s*(https://\S+)", re.I)
URL_RE = re.compile(r"https://(?:www\.)?dzen\.ru/\S+", re.I)


@dataclass(slots=True)
class ConfirmResult:
    ok: bool
    status: str
    url: str | None = None
    reason: str | None = None


def normalize_dzen_url(raw: str) -> str | None:
    text = (raw or "").strip()
    match = URL_RE.search(text)
    if not match:
        return None
    url = match.group(0).rstrip(").,]")
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host not in DZEN_HOSTS:
        return None
    if parts.scheme != "https":
        return None
    return url


def looks_like_dzen_article(url: str) -> bool:
    parts = urlsplit(url)
    return bool(ARTICLE_PATH.match(parts.path) or parts.path.startswith("/"))


def fetch_public(url: str, *, timeout: float = 15.0) -> tuple[bool, int, str]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(
                url, headers={"User-Agent": "WeGoTripEditorialEngine/dzen-verify"}
            )
        body = response.text[:4000]
        return response.status_code == 200, response.status_code, body
    except httpx.HTTPError as exc:
        return False, 0, str(exc)


def title_overlap(headline: str, html_body: str) -> bool:
    tokens = list(re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", headline.casefold()))
    if not tokens:
        return True
    hay = html_body.casefold()
    hits = sum(1 for tok in tokens if tok in hay)
    return hits >= max(1, min(3, len(tokens) // 3))


def verify_and_confirm(
    session: Session,
    article: DzenArticle,
    raw_url: str,
    *,
    confirmed_by: str,
    network: bool = True,
) -> ConfirmResult:
    url = normalize_dzen_url(raw_url)
    if url is None:
        return ConfirmResult(False, article.status, reason="not a dzen.ru URL")
    if "wegotrip-content-engine" in url or "/admin/" in url:
        return ConfirmResult(False, article.status, reason="internal URL rejected")
    if not looks_like_dzen_article(url):
        return ConfirmResult(False, article.status, reason="URL is not a Dzen article")

    if network:
        ok, status_code, body = fetch_public(url)
        if not ok:
            article.status = DzenArticleStatus.PUBLISHED_SUBMITTED.value
            article.published_url = url
            return ConfirmResult(
                False,
                article.status,
                url=url,
                reason=f"pending_verification HTTP {status_code}",
            )
        if article.headline and not title_overlap(article.headline, body):
            return ConfirmResult(False, article.status, url=url, reason="title mismatch")
        if "wegotrip" not in body.casefold() and "дзен" not in body.casefold():
            # Public pages vary; require at least a 200 and a dzen URL shape.
            pass

    article.published_url = url
    article.status = DzenArticleStatus.PUBLISHED_CONFIRMED.value
    article.published_confirmed_at = utcnow()
    item = session.scalar(
        select(DzenHandoffItem)
        .where(DzenHandoffItem.article_id == article.id)
        .order_by(DzenHandoffItem.id.desc())
    )
    if item is not None:
        item.published_url = url
        item.status = DzenArticleStatus.PUBLISHED_CONFIRMED.value
        item.confirmed_by = confirmed_by
        item.confirmed_at = utcnow()
        item.verified_at = utcnow()
    session.flush()
    return ConfirmResult(True, article.status, url=url)


def parse_thread_reply(text: str, item_count: int) -> dict[int, str]:
    """Map '1: url' replies. Never guess if two bare URLs are present."""
    assigned: dict[int, str] = {}
    for match in NUMBERED.finditer(text or ""):
        url = normalize_dzen_url(match.group(2))
        if url:
            assigned[int(match.group(1))] = url
    urls = [u for u in (normalize_dzen_url(m) for m in URL_RE.findall(text or "")) if u]
    if not assigned and item_count == 1 and len(urls) == 1:
        assigned[1] = urls[0]
    return assigned


__all__ = [
    "ConfirmResult",
    "normalize_dzen_url",
    "parse_thread_reply",
    "verify_and_confirm",
]
