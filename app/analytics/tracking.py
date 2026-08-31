"""Click tracking.

Every outbound product button can be routed through ``/r/<token>``, which counts the
click and 302s to the affiliate URL. The redirect target always keeps ``coupon=<id>``
and the UTM parameters, so attribution survives even if our redirect is bypassed.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings, get_settings
from app.db.models import Article, ClickEvent, TrackingLink
from app.errors import ValidationFailed
from app.links.affiliate import AffiliateLinkBuilder

TOKEN_BYTES = 9


@dataclass(slots=True)
class TrackedLink:
    token: str
    public_url: str
    target_url: str


class TrackingService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        link_builder: AffiliateLinkBuilder | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.links = link_builder or AffiliateLinkBuilder(self.settings)

    def public_url(self, token: str) -> str:
        return f"{self.settings.tracking_root}/r/{token}"

    def get_or_create(
        self,
        *,
        article: Article | None,
        market: Market,
        target_url: str,
        link_type: str = "product",
        product_external_id: str | None = None,
        entity_type: str | None = None,
        entity_external_id: str | None = None,
        placement: str | None = None,
    ) -> TrackedLink:
        if self.links.is_store_url(target_url) and not self.links.has_affiliate_marker(target_url):
            raise ValidationFailed(
                f"refusing to track a link without the affiliate marker: {target_url}"
            )

        existing = None
        if article is not None:
            existing = self.session.scalar(
                select(TrackingLink).where(
                    TrackingLink.article_id == article.id,
                    TrackingLink.product_external_id == product_external_id,
                    TrackingLink.placement == placement,
                    TrackingLink.link_type == link_type,
                )
            )
        if existing is not None:
            existing.target_url = target_url
            self.session.flush()
            return TrackedLink(existing.token, self.public_url(existing.token), target_url)

        token = secrets.token_urlsafe(TOKEN_BYTES)
        row = TrackingLink(
            token=token,
            article_id=article.id if article else None,
            market=market,
            target_url=target_url,
            link_type=link_type,
            entity_type=entity_type,
            entity_external_id=entity_external_id,
            product_external_id=product_external_id,
            placement=placement,
        )
        self.session.add(row)
        self.session.flush()
        return TrackedLink(token, self.public_url(token), target_url)

    def resolve(self, token: str) -> TrackingLink | None:
        return self.session.scalar(select(TrackingLink).where(TrackingLink.token == token))

    def record_click(
        self,
        link: TrackingLink,
        *,
        visitor_hash: str | None = None,
        user_agent: str | None = None,
        referer: str | None = None,
    ) -> ClickEvent:
        is_unique = True
        if visitor_hash:
            seen = self.session.scalar(
                select(ClickEvent).where(
                    ClickEvent.tracking_link_id == link.id,
                    ClickEvent.visitor_hash == visitor_hash,
                )
            )
            is_unique = seen is None
        link.clicks += 1
        if is_unique:
            link.unique_clicks += 1
        event = ClickEvent(
            tracking_link_id=link.id,
            article_id=link.article_id,
            market=link.market,
            visitor_hash=visitor_hash,
            user_agent=(user_agent or "")[:500] or None,
            referer=(referer or "")[:500] or None,
            is_unique=is_unique,
        )
        self.session.add(event)
        self.session.flush()
        return event


def visitor_fingerprint(ip: str | None, user_agent: str | None) -> str | None:
    """Coarse, non-reversible visitor key — no raw IP is ever stored."""
    if not ip and not user_agent:
        return None
    blob = f"{ip or ''}|{(user_agent or '')[:200]}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


__all__ = ["TrackedLink", "TrackingService", "visitor_fingerprint"]
