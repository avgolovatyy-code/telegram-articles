"""Affiliate API normalization, locale segmentation and the entity graph."""

from __future__ import annotations

import pytest

from app.catalog.mock import MockCatalogProvider
from app.catalog.normalize import (
    normalize_attraction,
    normalize_city,
    normalize_country,
    normalize_product,
    parse_page,
    unwrap,
)
from app.catalog.sync import CatalogSyncService
from app.db.models import Attraction, Category, City, Collection, Country, Product
from app.errors import CatalogSchemaError


def test_unwrap_handles_v2_and_v3_shapes():
    assert unwrap({"data": {"results": []}}) == {"results": []}
    assert unwrap({"results": [], "count": 0}) == {"results": [], "count": 0}


def test_parse_page_reads_pagination():
    page = parse_page({"data": {"count": 7, "pages": 2, "current": 1, "next": 2, "results": [{}]}})
    assert (page.count, page.pages, page.current, page.next) == (7, 2, 1, 2)


def test_parse_page_rejects_unknown_shape():
    with pytest.raises(CatalogSchemaError):
        parse_page({"data": {"items": []}})


def test_normalize_country_keeps_code_and_slug():
    country = normalize_country(
        {"id": 3017382, "code": "FR", "name": "France", "slug": "france"}, "en"
    )
    assert country.external_id == "3017382"
    assert country.code == "FR"


def test_normalize_city_reads_country_string():
    city = normalize_city(
        {"id": 2988507, "name": "Paris", "slug": "paris", "itemsCount": 112, "country": "France"},
        "en",
        rank=1,
    )
    assert city.country_name == "France"
    assert city.product_count == 112


def test_normalize_attraction_builds_media_from_preview():
    attraction = normalize_attraction(
        {"id": 2285, "name": "The Louvre", "slug": "musee-du-louvre", "preview": "https://x/y.jpg"},
        "en",
        city_external_id="2988507",
    )
    assert attraction.media[0].url == "https://x/y.jpg"
    assert attraction.city_external_id == "2988507"


def test_normalize_product_maps_taxonomy_and_leaves_unknown_fields_none():
    raw = {
        "id": 63,
        "slug": "tour",
        "title": "Tour",
        "locale": "en",
        "durationMin": 90,
        "durationMax": 120,
        "price": 17.57,
        "currencyCode": "USD",
        "categories": [{"id": 3, "title": "Theme Tours", "slug": "theme-tours"}],
        "subcategories": [{"id": 12, "title": "Movie & TV Tours", "slug": "movie-tv-tours"}],
        "attractions": [{"id": 61, "name": "Edinburgh Castle", "slug": "edinburgh-castle"}],
        "city": {"id": 10, "name": "Edinburgh", "slug": "edinburgh"},
        "country": {"id": 2635167, "name": "United Kingdom", "slug": "united-kingdom"},
    }
    product = normalize_product(raw, "en", has_detail=True)
    assert product.duration_min == 90 and product.duration_max == 120
    assert [c.title for c in product.categories] == ["Theme Tours"]
    assert [c.title for c in product.collections] == ["Movie & TV Tours"]
    assert [a.name for a in product.attractions] == ["Edinburgh Castle"]
    assert product.city_external_id == "10"
    assert product.country_external_id == "2635167"
    # The Affiliate API documents no audio preview URL.
    assert product.audio_preview_url is None
    assert product.rating is None


def test_normalize_product_requires_an_id():
    with pytest.raises(CatalogSchemaError):
        normalize_product({"title": "no id"}, "en")


def test_available_falls_back_to_tags():
    product = normalize_product({"id": 1, "title": "t", "tags": {"available": False}}, "en")
    assert product.available is False


# ------------------------------------------------------------------ sync tests
def test_sync_creates_separate_rows_per_market(
    session, mock_catalog: MockCatalogProvider, settings
):
    service = CatalogSyncService(session, mock_catalog, settings=settings)
    en = service.sync_market("en")
    ru = service.sync_market("ru")

    assert en.products > 0 and ru.products > 0
    assert not en.errors and not ru.errors

    paris_en = session.query(City).filter_by(market="en", external_id="2988507").one()
    paris_ru = session.query(City).filter_by(market="ru", external_id="2988507").one()
    assert paris_en.name == "Paris"
    assert paris_ru.name == "Париж"


def test_sync_populates_every_catalogue_level(synced_session):
    for model in (Country, City, Attraction, Product):
        for market in ("en", "ru"):
            assert synced_session.query(model).filter_by(market=market).count() > 0
    # Categories and collections are derived from product details.
    assert synced_session.query(Category).filter_by(market="en").count() > 0
    assert synced_session.query(Collection).filter_by(market="en").count() > 0


def test_products_never_mix_markets(synced_session):
    for market in ("en", "ru"):
        products = synced_session.query(Product).filter_by(market=market).all()
        assert products
        assert all(p.market == market for p in products)
        assert all(p.locale in (market, None) for p in products)


def test_detail_sync_records_a_snapshot_and_links(synced_session):
    detailed = (
        synced_session.query(Product)
        .filter(Product.market == "en", Product.detail_fetched_at.is_not(None))
        .first()
    )
    assert detailed is not None
    assert detailed.snapshot_id
    assert detailed.canonical_url
    assert detailed.media_items


def test_recount_updates_inventory_depth(synced_session):
    city = (
        synced_session.query(City)
        .filter_by(market="en")
        .order_by(City.product_count.desc())
        .first()
    )
    assert city.product_count > 0
