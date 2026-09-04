"""WeGoTrip API host selection and RU domestic catalogue helpers."""

from __future__ import annotations


def test_api_base_url_uses_ru_host_for_russian_market(settings):
    assert "wegotrip.ru" in settings.api_base_url("ru")
    assert "wegotrip.com" in settings.api_base_url("en")
    assert settings.api_base_url("ru") != settings.api_base_url("en")


def test_http_provider_builds_market_specific_urls(settings):
    from app.catalog.wegotrip import WeGoTripHttpProvider

    provider = WeGoTripHttpProvider(settings)
    try:
        ru = provider._url("cities", "v2", market="ru")
        en = provider._url("cities", "v2", market="en")
        assert ru.startswith("https://wegotrip.ru/api/")
        assert en.startswith("https://app.wegotrip.com/api/")
        assert ru.endswith("/v2/cities/")
    finally:
        provider.close()
