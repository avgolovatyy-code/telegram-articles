"""AffiliateLinkBuilder: coupon=435 must survive every path (spec §26, §51)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from app.links.affiliate import AffiliateLinkBuilder, LinkContext


@pytest.fixture()
def builder(settings) -> AffiliateLinkBuilder:
    return AffiliateLinkBuilder(settings)


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def test_coupon_added_to_plain_url(builder: AffiliateLinkBuilder):
    url = builder.decorate("https://wegotrip.ru/barcelona-d3128760/")
    assert url == "https://wegotrip.ru/barcelona-d3128760/?coupon=435"


def test_existing_query_is_preserved_with_ampersand(builder: AffiliateLinkBuilder):
    url = builder.decorate("https://wegotrip.com/paris-d2988507/?lang=en&sort=popular")
    assert url.count("?") == 1
    assert "&" in url
    query = query_of(url)
    assert query["coupon"] == ["435"]
    assert query["lang"] == ["en"]
    assert query["sort"] == ["popular"]


def test_stale_coupon_is_replaced(builder: AffiliateLinkBuilder):
    url = builder.decorate("https://wegotrip.com/paris-d2988507/?coupon=1005")
    assert query_of(url)["coupon"] == ["435"]


def test_coupon_comes_before_utm(builder: AffiliateLinkBuilder):
    url = builder.decorate(
        "https://wegotrip.com/paris-d2988507/",
        LinkContext(market="en", article_id="abc123", topic_slug="en-paris-things-to-do"),
    )
    assert urlsplit(url).query.startswith("coupon=435&utm_source=telegram")
    query = query_of(url)
    assert query["utm_medium"] == ["content"]
    assert query["utm_campaign"] == ["wegotrip_en"]
    assert query["utm_content"] == ["abc123"]
    assert query["utm_term"] == ["en-paris-things-to-do"]


def test_ru_campaign_and_domain(builder: AffiliateLinkBuilder):
    url = builder.city_url(
        "ru", "barcelona", 3128760, LinkContext(market="ru", article_id="x", topic_slug="t")
    )
    assert url.startswith("https://wegotrip.ru/barcelona-d3128760/")
    assert query_of(url)["utm_campaign"] == ["wegotrip_ru"]


def test_product_url_follows_documented_structure(builder: AffiliateLinkBuilder):
    url = builder.product_url(
        "en",
        product_slug="edinburgh-harry-potter-tour",
        product_id=63,
        city_slug="edinburgh",
        city_id=10,
    )
    assert url == ("https://wegotrip.com/edinburgh-d10/edinburgh-harry-potter-tour-p63/?coupon=435")


def test_canonical_url_is_retargeted_to_the_market_domain(builder: AffiliateLinkBuilder):
    url = builder.product_url(
        "ru",
        product_slug="ignored",
        product_id=15956,
        canonical_url="https://wegotrip.com/barcelona-d3128760/monzhuik-p15956/",
    )
    assert url.startswith("https://wegotrip.ru/barcelona-d3128760/monzhuik-p15956/")
    assert builder.has_affiliate_marker(url)


def test_checkout_url(builder: AffiliateLinkBuilder):
    url = builder.checkout_url("en", product_slug="tour", product_id=63)
    assert url == "https://wegotrip.com/checkout/tour-p63/booking/?coupon=435"


def test_marker_detection(builder: AffiliateLinkBuilder):
    assert builder.has_affiliate_marker("https://wegotrip.com/x/?coupon=435")
    assert not builder.has_affiliate_marker("https://wegotrip.com/x/?coupon=1005")
    assert not builder.has_affiliate_marker("https://wegotrip.com/x/")


def test_store_url_detection(builder: AffiliateLinkBuilder):
    assert builder.is_store_url("https://wegotrip.com/x/")
    assert builder.is_store_url("https://www.wegotrip.ru/x/")
    assert not builder.is_store_url("https://example.com/x/")


def test_relative_url_is_rejected(builder: AffiliateLinkBuilder):
    with pytest.raises(ValueError, match="non-absolute"):
        builder.decorate("/barcelona-d3128760/")


def test_fragment_is_preserved(builder: AffiliateLinkBuilder):
    url = builder.decorate("https://wegotrip.com/paris-d2988507/#reviews")
    assert url.endswith("#reviews")
    assert query_of(url)["coupon"] == ["435"]
