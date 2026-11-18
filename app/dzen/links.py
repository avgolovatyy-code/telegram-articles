"""WeGoTrip product URLs for Dzen: coupon=435 exactly once, never on images."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from app.config import Settings, get_settings
from app.links.affiliate import AffiliateLinkBuilder, LinkContext

DZEN_UTM_SOURCE = "dzen"
DZEN_UTM_MEDIUM = "editorial"
DZEN_UTM_CAMPAIGN = "dzen_ru"


def dzen_link_context(article_id: str, topic_slug: str | None = None) -> LinkContext:
    return LinkContext(
        market="ru",
        article_id=article_id,
        topic_slug=topic_slug,
        utm_source=DZEN_UTM_SOURCE,
        utm_medium=DZEN_UTM_MEDIUM,
        utm_campaign=DZEN_UTM_CAMPAIGN,
    )


def product_affiliate_url(
    *,
    canonical_url: str | None,
    product_slug: str,
    product_id: str | int,
    article_id: str,
    topic_slug: str | None = None,
    city_slug: str | None = None,
    city_id: str | int | None = None,
    settings: Settings | None = None,
) -> str:
    builder = AffiliateLinkBuilder(settings or get_settings())
    url = builder.product_url(
        "ru",
        product_slug=product_slug,
        product_id=product_id,
        city_slug=city_slug,
        city_id=city_id,
        canonical_url=canonical_url,
        context=dzen_link_context(article_id, topic_slug),
    )
    assert_valid_product_url(url, referer_id=builder.referer_id)
    return url


def assert_valid_product_url(url: str, *, referer_id: str = "435") -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ValueError(f"product URL must be https: {url}")
    query = parse_qs(parts.query)
    coupons = query.get("coupon", [])
    if coupons != [referer_id]:
        raise ValueError(f"coupon must appear exactly once as {referer_id}: {url}")
    if query.get("utm_source") != [DZEN_UTM_SOURCE]:
        raise ValueError(f"utm_source must be {DZEN_UTM_SOURCE}: {url}")


def coupon_count(url: str) -> int:
    return len(parse_qs(urlsplit(url).query).get("coupon", []))


def image_url_is_clean(url: str) -> bool:
    if not url.startswith("https://"):
        return False
    return "coupon=" not in urlsplit(url).query.lower()


__all__ = [
    "DZEN_UTM_CAMPAIGN",
    "DZEN_UTM_MEDIUM",
    "DZEN_UTM_SOURCE",
    "assert_valid_product_url",
    "coupon_count",
    "dzen_link_context",
    "image_url_is_clean",
    "product_affiliate_url",
]
