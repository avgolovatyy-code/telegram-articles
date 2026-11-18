from __future__ import annotations

import pytest

from app.dzen.links import (
    assert_valid_product_url,
    coupon_count,
    image_url_is_clean,
    product_affiliate_url,
)


def test_product_url_has_single_coupon_and_dzen_utm(settings):
    url = product_affiliate_url(
        canonical_url="https://wegotrip.ru/istanbul-d1/audio-p42/",
        product_slug="audio",
        product_id="42",
        article_id="dzen_1",
        topic_slug="istanbul",
        settings=settings,
    )
    assert coupon_count(url) == 1
    assert "coupon=435" in url
    assert "utm_source=dzen" in url
    assert "utm_medium=editorial" in url
    assert "utm_campaign=dzen_ru" in url
    assert_valid_product_url(url)


def test_image_urls_must_not_get_coupon():
    assert image_url_is_clean("https://cdn.example/cover.jpg") is True
    assert image_url_is_clean("https://cdn.example/cover.jpg?coupon=435") is False
    assert image_url_is_clean("http://cdn.example/cover.jpg") is False


def test_duplicate_coupon_rejected():
    with pytest.raises(ValueError):
        assert_valid_product_url("https://wegotrip.ru/p/?coupon=435&coupon=435&utm_source=dzen")
