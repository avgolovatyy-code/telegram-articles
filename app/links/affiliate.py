"""The single place where WeGoTrip store URLs are built.

Nothing else in the codebase — and certainly no LLM prompt or LLM output — may
assemble a wegotrip.com / wegotrip.ru link. Every URL produced here carries the
affiliate marker ``coupon=<REFERER_ID>`` and, when an article context is supplied,
the UTM parameters required for attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.config import Market, Settings, get_settings

COUPON_PARAM = "coupon"

#: Order in which analytics parameters are appended after ``coupon``.
_UTM_ORDER = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


@dataclass(frozen=True, slots=True)
class LinkContext:
    """Attribution context for one outbound link."""

    market: Market
    article_id: str | None = None
    topic_slug: str | None = None

    def utm_params(self, settings: Settings) -> dict[str, str]:
        params = {
            "utm_source": settings.utm_source,
            "utm_medium": settings.utm_medium,
            "utm_campaign": settings.utm_campaign(self.market),
        }
        if self.article_id:
            params["utm_content"] = str(self.article_id)
        if self.topic_slug:
            params["utm_term"] = self.topic_slug
        return params


class AffiliateLinkBuilder:
    """Builds and repairs WeGoTrip affiliate URLs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------ core
    @property
    def referer_id(self) -> str:
        return self._settings.wegotrip_referer_id

    def domain(self, market: Market) -> str:
        return self._settings.store_domain(market)

    def decorate(self, url: str, context: LinkContext | None = None) -> str:
        """Add ``coupon`` (and UTMs) to an arbitrary WeGoTrip URL.

        Existing query parameters are preserved. ``coupon`` is always forced to the
        configured referer id — an inherited or stale coupon never survives.
        """
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            raise ValueError(f"Cannot decorate a non-absolute URL: {url!r}")

        existing = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        managed = {COUPON_PARAM, *_UTM_ORDER}
        preserved = [(k, v) for k, v in existing if k not in managed]

        query: list[tuple[str, str]] = [(COUPON_PARAM, self.referer_id)]
        if context is not None:
            utms = context.utm_params(self._settings)
            query.extend((key, utms[key]) for key in _UTM_ORDER if key in utms)
        query.extend(preserved)

        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query, safe="@:/"), parts.fragment)
        )

    def retarget_domain(self, url: str, market: Market) -> str:
        """Point a store URL at the domain that serves ``market``."""
        parts = urlsplit(url)
        target = self.domain(market)
        if parts.netloc.lower().removeprefix("www.") == target:
            return url
        return urlunsplit(
            (parts.scheme or "https", target, parts.path, parts.query, parts.fragment)
        )

    # -------------------------------------------------------------- builders
    def _base(self, market: Market, path: str) -> str:
        path = "/" + path.strip("/") + "/"
        return f"https://{self.domain(market)}{path}"

    @staticmethod
    def city_path(city_slug: str, city_id: str | int) -> str:
        return f"{city_slug}-d{city_id}"

    @staticmethod
    def product_path(product_slug: str, product_id: str | int) -> str:
        return f"{product_slug}-p{product_id}"

    def city_url(
        self,
        market: Market,
        city_slug: str,
        city_id: str | int,
        context: LinkContext | None = None,
    ) -> str:
        return self.decorate(self._base(market, self.city_path(city_slug, city_id)), context)

    def product_url(
        self,
        market: Market,
        *,
        product_slug: str,
        product_id: str | int,
        city_slug: str | None = None,
        city_id: str | int | None = None,
        canonical_url: str | None = None,
        context: LinkContext | None = None,
    ) -> str:
        """Product page URL.

        The Affiliate API returns a canonical ``url`` for product details; it is
        preferred (it already encodes the correct city segment) and only rewritten
        to the market domain. Without it the documented
        ``/{city-slug}-d{city-id}/{product-slug}-p{product-id}/`` shape is used.
        """
        if canonical_url:
            return self.decorate(self.retarget_domain(canonical_url, market), context)
        product_segment = self.product_path(product_slug, product_id)
        if city_slug and city_id is not None:
            path = f"{self.city_path(city_slug, city_id)}/{product_segment}"
        else:
            path = product_segment
        return self.decorate(self._base(market, path), context)

    def checkout_url(
        self,
        market: Market,
        *,
        product_slug: str,
        product_id: str | int,
        context: LinkContext | None = None,
    ) -> str:
        path = f"checkout/{self.product_path(product_slug, product_id)}/booking"
        return self.decorate(self._base(market, path), context)

    def attraction_url(
        self,
        market: Market,
        *,
        city_slug: str,
        city_id: str | int,
        attraction_slug: str,
        attraction_id: str | int,
        context: LinkContext | None = None,
    ) -> str:
        path = f"{self.city_path(city_slug, city_id)}/{attraction_slug}-a{attraction_id}"
        return self.decorate(self._base(market, path), context)

    def category_url(
        self,
        market: Market,
        *,
        category_slug: str,
        city_slug: str | None = None,
        city_id: str | int | None = None,
        context: LinkContext | None = None,
    ) -> str:
        if city_slug and city_id is not None:
            path = f"{self.city_path(city_slug, city_id)}/{category_slug}"
        else:
            path = category_slug
        return self.decorate(self._base(market, path), context)

    def collection_url(
        self,
        market: Market,
        *,
        collection_slug: str,
        city_slug: str | None = None,
        city_id: str | int | None = None,
        context: LinkContext | None = None,
    ) -> str:
        return self.category_url(
            market,
            category_slug=collection_slug,
            city_slug=city_slug,
            city_id=city_id,
            context=context,
        )

    def country_url(
        self, market: Market, *, country_slug: str, context: LinkContext | None = None
    ) -> str:
        return self.decorate(self._base(market, country_slug), context)

    def landing_url(
        self, market: Market, *, path: str = "", context: LinkContext | None = None
    ) -> str:
        return self.decorate(
            self._base(market, path) if path else f"https://{self.domain(market)}/", context
        )

    # ------------------------------------------------------------ validation
    def has_affiliate_marker(self, url: str) -> bool:
        query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        return query.get(COUPON_PARAM) == self.referer_id

    def is_store_url(self, url: str) -> bool:
        host = urlsplit(url).netloc.lower()
        host = host.removeprefix("www.")
        return host in {
            self._settings.wegotrip_store_domain_en,
            self._settings.wegotrip_store_domain_ru,
        }


_builder: AffiliateLinkBuilder | None = None


def get_link_builder(settings: Settings | None = None) -> AffiliateLinkBuilder:
    global _builder
    if settings is not None:
        return AffiliateLinkBuilder(settings)
    if _builder is None:
        _builder = AffiliateLinkBuilder()
    return _builder


def reset_link_builder() -> None:
    global _builder
    _builder = None


__all__ = [
    "COUPON_PARAM",
    "AffiliateLinkBuilder",
    "LinkContext",
    "get_link_builder",
    "reset_link_builder",
]
