"""Catalog synchronisation.

EN and RU are synchronised independently: the Affiliate API returns different
entity names, product sets and inventory depth per ``lang``, so each market gets its
own rows keyed by ``(market, external_id)``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.provider import (
    AudioPreviewProvider,
    NullAudioPreviewProvider,
    WeGoTripCatalogProvider,
)
from app.catalog.schemas import NormalizedProduct
from app.config import Market, Settings, get_settings
from app.db.models import (
    Attraction,
    CatalogSnapshot,
    Category,
    City,
    Collection,
    Country,
    Product,
    ProductAttraction,
    ProductCategory,
    ProductCollection,
    ProductMedia,
    SyncRun,
)
from app.db.types import utcnow
from app.errors import CatalogError
from app.logging_setup import get_logger, job_context, new_job_id

log = get_logger("catalog.sync")


@dataclass(slots=True)
class SyncStats:
    countries: int = 0
    cities: int = 0
    attractions: int = 0
    categories: int = 0
    collections: int = 0
    products: int = 0
    product_details: int = 0
    products_deactivated: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "countries": self.countries,
            "cities": self.cities,
            "attractions": self.attractions,
            "categories": self.categories,
            "collections": self.collections,
            "products": self.products,
            "product_details": self.product_details,
            "products_deactivated": self.products_deactivated,
            "errors": self.errors[:20],
        }


@dataclass(slots=True)
class SyncOptions:
    """Bounds the number of upstream calls a single sync performs."""

    cities_for_attractions: int = 25
    max_products: int | None = 400
    detail_products: int = 60
    detail_max_age_hours: int = 72
    deactivate_missing: bool = True


def snapshot_id(market: Market, entity_type: str, external_id: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:24]
    return f"{market}:{entity_type}:{external_id}:{digest}"


class CatalogSyncService:
    def __init__(
        self,
        session: Session,
        provider: WeGoTripCatalogProvider,
        *,
        settings: Settings | None = None,
        audio_provider: AudioPreviewProvider | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.settings = settings or get_settings()
        self.audio_provider = audio_provider or NullAudioPreviewProvider()

    # ------------------------------------------------------------------ main
    def sync_market(self, market: Market, options: SyncOptions | None = None) -> SyncStats:
        options = options or SyncOptions()
        stats = SyncStats()
        job_id = new_job_id("sync")
        run = SyncRun(job_id=job_id, market=market, status="running")
        self.session.add(run)
        self.session.flush()

        with job_context("catalog.sync", job_id=job_id, market=market):
            try:
                self._sync_countries(market, stats)
                city_ids = self._sync_cities(market, stats)
                self._sync_attractions(market, city_ids[: options.cities_for_attractions], stats)
                product_ids = self._sync_products(market, stats, options)
                self._sync_product_details(market, product_ids, stats, options)
                self._recount(market)
                run.status = "ok"
            except CatalogError as exc:
                stats.errors.append(str(exc))
                run.status = "failed"
                run.error = str(exc)
                log.error("catalog.sync_failed", market=market, error=str(exc))
            finally:
                run.finished_at = utcnow()
                run.stats = stats.as_dict()
                self.session.flush()
        return stats

    # ------------------------------------------------------------- entities
    def _sync_countries(self, market: Market, stats: SyncStats) -> None:
        for country in self.provider.get_countries(market):
            row = self._get_or_create(Country, market, country.external_id)
            row.slug = country.slug
            row.name = country.name
            row.code = country.code
            row.media = [asset.model_dump() for asset in country.media]
            row.popularity_rank = country.popularity_rank
            row.raw = country.raw
            row.last_seen_at = utcnow()
            stats.countries += 1
        self.session.flush()

    def _sync_cities(self, market: Market, stats: SyncStats) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        cities = list(self.provider.get_cities(market))
        if market == "ru":
            # Domestic destinations are missing from the .com API and easy to
            # under-sample on a global popular list — pull Russia explicitly.
            russia_id = self._russia_country_id(market)
            if russia_id:
                cities.extend(
                    self.provider.get_cities(market, country_id=russia_id, popular=False)
                )
        for city in cities:
            if city.external_id in seen:
                row = self._find(City, market, city.external_id)
                if row is not None:
                    if (city.product_count or 0) > (row.product_count or 0):
                        row.product_count = city.product_count
                        row.raw = city.raw or row.raw
                    country_id = city.country_external_id or self._resolve_country_id(
                        market, city.country_name
                    )
                    row.country_external_id = (
                        country_id or row.country_external_id
                    )
                    row.country_name = city.country_name or row.country_name
                continue
            seen.add(city.external_id)
            row = self._get_or_create(City, market, city.external_id)
            row.slug = city.slug
            row.name = city.name
            country_id = city.country_external_id or self._resolve_country_id(
                market, city.country_name
            )
            row.country_external_id = country_id or row.country_external_id
            row.country_name = city.country_name or row.country_name
            row.popular = city.popular
            row.media = [asset.model_dump() for asset in city.media]
            row.product_count = city.product_count
            row.popularity_rank = city.popularity_rank
            row.raw = city.raw
            row.last_seen_at = utcnow()
            ids.append(city.external_id)
            stats.cities += 1
        self.session.flush()
        return self._prioritized_city_ids(market, ids)

    def _russia_country_id(self, market: Market) -> str | None:
        row = self.session.scalar(
            select(Country).where(Country.market == market, Country.code == "RU")
        )
        if row is not None:
            return row.external_id
        row = self.session.scalar(
            select(Country).where(
                Country.market == market,
                Country.name.in_(("Россия", "Russia", "Russian Federation")),
            )
        )
        return row.external_id if row is not None else None

    def _resolve_country_id(self, market: Market, country_name: str | None) -> str | None:
        """Map a bare country name (common on wegotrip.ru city payloads) to an id."""
        if not country_name:
            return None
        if not hasattr(self, "_country_name_index"):
            self._country_name_index: dict[tuple[str, str], str] = {}
            self._country_name_markets: set[str] = set()
        if market not in self._country_name_markets:
            for row in self.session.scalars(select(Country).where(Country.market == market)):
                if row.name:
                    self._country_name_index[(market, row.name.casefold())] = row.external_id
            self._country_name_markets.add(market)
        return self._country_name_index.get((market, country_name.casefold()))

    def _prioritized_city_ids(self, market: Market, ids: list[str]) -> list[str]:
        """Prefer Russia (for RU market), then deeper inventory, for attraction sync."""
        if not ids:
            return ids
        rows = list(
            self.session.scalars(
                select(City).where(City.market == market, City.external_id.in_(ids))
            )
        )
        by_id = {row.external_id: row for row in rows}
        russia_id = self._russia_country_id(market) if market == "ru" else None

        def sort_key(city_id: str) -> tuple[int, int, str]:
            row = by_id.get(city_id)
            if row is None:
                return (1, 0, city_id)
            domestic = 0 if (russia_id and row.country_external_id == russia_id) else 1
            return (domestic, -(row.product_count or 0), city_id)

        return sorted(ids, key=sort_key)

    def _sync_attractions(self, market: Market, city_ids: list[str], stats: SyncStats) -> None:
        for city_id in city_ids:
            try:
                attractions = self.provider.get_attractions(market, city_id=city_id)
            except CatalogError as exc:
                stats.errors.append(f"attractions[{city_id}]: {exc}")
                continue
            for attraction in attractions:
                row = self._get_or_create(Attraction, market, attraction.external_id)
                row.slug = attraction.slug
                row.name = attraction.name
                row.city_external_id = attraction.city_external_id or city_id
                row.preview = attraction.preview
                row.media = [asset.model_dump() for asset in attraction.media]
                row.product_count = attraction.product_count
                row.popularity_rank = attraction.popularity_rank
                row.raw = attraction.raw
                row.last_seen_at = utcnow()
                stats.attractions += 1
            self.session.flush()

    def _sync_products(self, market: Market, stats: SyncStats, options: SyncOptions) -> list[str]:
        started = utcnow()
        products = list(self.provider.get_products(market, max_items=options.max_products))
        if market == "ru":
            russia_id = self._russia_country_id(market)
            if russia_id:
                # Reserve a dedicated Russia slice so domestic topics are not crowded
                # out of the global popular cap.
                domestic_cap = options.max_products or 400
                products.extend(
                    self.provider.get_products(
                        market, country_id=russia_id, max_items=domestic_cap
                    )
                )
        seen: list[str] = []
        seen_set: set[str] = set()
        for product in products:
            if product.external_id in seen_set:
                continue
            seen_set.add(product.external_id)
            self._upsert_product(product, market, detail=False)
            seen.append(product.external_id)
            stats.products += 1
        self.session.flush()

        if options.deactivate_missing and seen:
            stale = self.session.scalars(
                select(Product).where(
                    Product.market == market,
                    Product.last_seen_at < started,
                    Product.available.is_(True),
                )
            ).all()
            for row in stale:
                row.available = False
                stats.products_deactivated += 1
        return seen

    def _sync_product_details(
        self,
        market: Market,
        product_ids: list[str],
        stats: SyncStats,
        options: SyncOptions,
    ) -> None:
        cutoff = utcnow() - dt.timedelta(hours=options.detail_max_age_hours)
        candidates: list[str] = []
        for external_id in product_ids:
            row = self._find(Product, market, external_id)
            if row is None:
                continue
            if row.detail_fetched_at is None or row.detail_fetched_at < cutoff:
                candidates.append(external_id)
            if len(candidates) >= options.detail_products:
                break

        for external_id in candidates:
            try:
                detail = self.provider.get_product(external_id, market)
            except CatalogError as exc:
                stats.errors.append(f"product[{external_id}]: {exc}")
                continue
            if detail is None:
                continue
            self._upsert_product(detail, market, detail=True, stats=stats)
            stats.product_details += 1
            self.session.flush()

    # ----------------------------------------------------------- persistence
    def _upsert_product(
        self,
        product: NormalizedProduct,
        market: Market,
        *,
        detail: bool,
        stats: SyncStats | None = None,
    ) -> Product:
        row = self._get_or_create(Product, market, product.external_id)
        row.slug = product.slug
        row.title = product.title
        row.locale = product.locale or market
        row.cover = product.cover or row.cover
        row.preview = product.preview or row.preview
        row.price = product.price if product.price is not None else row.price
        row.exprice = product.exprice if product.exprice is not None else row.exprice
        row.currency_code = product.currency_code or row.currency_code
        row.currency_symbol = product.currency_symbol or row.currency_symbol
        row.rating = product.rating if product.rating is not None else row.rating
        row.reviews_count = (
            product.reviews_count if product.reviews_count is not None else row.reviews_count
        )
        row.ratings_count = (
            product.ratings_count if product.ratings_count is not None else row.ratings_count
        )
        row.duration_min = (
            product.duration_min if product.duration_min is not None else row.duration_min
        )
        row.duration_max = (
            product.duration_max if product.duration_max is not None else row.duration_max
        )
        row.duration_text = product.duration_text or row.duration_text
        row.available = product.available
        row.published = product.published
        row.tags = product.tags or row.tags
        row.types = product.types or row.types
        row.city_external_id = product.city_external_id or row.city_external_id
        row.country_external_id = product.country_external_id or row.country_external_id
        row.primary_category = product.primary_category or row.primary_category
        row.popularity_rank = (
            product.popularity_rank if product.popularity_rank is not None else row.popularity_rank
        )
        row.last_seen_at = utcnow()

        if detail:
            row.description = product.description
            row.short_description = product.short_description
            row.highlights = product.highlights
            row.images = [asset.model_dump() for asset in product.images]
            row.distance = product.distance
            row.inclusions = product.inclusions
            row.exclusions = product.exclusions
            row.important_info = product.important_info
            row.address = product.address
            row.start_location = product.start_location
            row.location_geo = product.location_geo
            row.reviews = [review.model_dump() for review in product.reviews]
            row.canonical_url = product.canonical_url or row.canonical_url
            row.api_updated_at = product.api_updated_at or row.api_updated_at
            row.audio_preview_url = (
                product.audio_preview_url or self.audio_provider.get_audio_preview(product)
            )
            row.detail_fetched_at = utcnow()
            row.raw = product.raw
            row.snapshot_id = self._store_snapshot(
                market, "product", product.external_id, product.raw
            )
            self._sync_product_links(row, product, market, stats)
            self._sync_product_media(row, product)

        self.session.flush()
        return row

    def _sync_product_links(
        self,
        row: Product,
        product: NormalizedProduct,
        market: Market,
        stats: SyncStats | None,
    ) -> None:
        existing_categories = {link.category_external_id for link in row.categories}
        for category in product.categories:
            self._upsert_taxonomy(
                Category, market, category.external_id, category.slug, category.title
            )
            if category.external_id not in existing_categories:
                row.categories.append(
                    ProductCategory(
                        category_external_id=category.external_id,
                        title=category.title,
                        slug=category.slug,
                    )
                )
                if stats:
                    stats.categories += 1

        existing_collections = {link.collection_external_id for link in row.collections}
        for collection in product.collections:
            self._upsert_taxonomy(
                Collection, market, collection.external_id, collection.slug, collection.title
            )
            if collection.external_id not in existing_collections:
                row.collections.append(
                    ProductCollection(
                        collection_external_id=collection.external_id,
                        title=collection.title,
                        slug=collection.slug,
                    )
                )
                if stats:
                    stats.collections += 1

        existing_attractions = {link.attraction_external_id for link in row.attractions}
        for attraction in product.attractions:
            attraction_row = self._get_or_create(Attraction, market, attraction.external_id)
            attraction_row.slug = attraction.slug or attraction_row.slug
            attraction_row.name = attraction.name or attraction_row.name
            attraction_row.city_external_id = (
                attraction.city_external_id
                or product.city_external_id
                or attraction_row.city_external_id
            )
            attraction_row.preview = attraction.preview or attraction_row.preview
            if attraction.media:
                attraction_row.media = [asset.model_dump() for asset in attraction.media]
            attraction_row.last_seen_at = utcnow()
            if attraction.external_id not in existing_attractions:
                row.attractions.append(
                    ProductAttraction(
                        attraction_external_id=attraction.external_id,
                        name=attraction.name,
                        slug=attraction.slug,
                    )
                )

    def _sync_product_media(self, row: Product, product: NormalizedProduct) -> None:
        row.media_items.clear()
        self.session.flush()
        for position, asset in enumerate(product.media):
            row.media_items.append(
                ProductMedia(
                    kind=asset.kind,
                    url=asset.url,
                    preview_url=asset.preview_url,
                    description=asset.description,
                    is_cover=asset.is_cover,
                    position=position,
                )
            )
        if product.audio_preview_url:
            row.media_items.append(
                ProductMedia(
                    kind="audio",
                    url=product.audio_preview_url,
                    position=len(product.media),
                )
            )

    def _upsert_taxonomy(
        self,
        model: type[Category] | type[Collection],
        market: Market,
        external_id: str,
        slug: str,
        title: str,
    ) -> None:
        row = self._find(model, market, external_id)
        if row is None:
            row = model(market=market, external_id=external_id, slug=slug, title=title)
            self.session.add(row)
        row.slug = slug
        row.title = title
        row.last_seen_at = utcnow()

    def _store_snapshot(
        self, market: Market, entity_type: str, external_id: str, payload: dict[str, Any]
    ) -> str:
        sid = snapshot_id(market, entity_type, external_id, payload)
        if self.session.get(CatalogSnapshot, sid) is None:
            self.session.add(
                CatalogSnapshot(
                    id=sid,
                    market=market,
                    entity_type=entity_type,
                    entity_external_id=external_id,
                    payload=payload,
                )
            )
        return sid

    # ------------------------------------------------------------- counters
    def _recount(self, market: Market) -> None:
        """Recompute inventory depth used by topic scoring."""
        products = self.session.scalars(
            select(Product).where(Product.market == market, Product.available.is_(True))
        ).all()

        by_city: dict[str, int] = {}
        by_country: dict[str, int] = {}
        by_attraction: dict[str, int] = {}
        by_category: dict[str, int] = {}
        by_collection: dict[str, int] = {}

        for product in products:
            if product.city_external_id:
                by_city[product.city_external_id] = by_city.get(product.city_external_id, 0) + 1
            if product.country_external_id:
                by_country[product.country_external_id] = (
                    by_country.get(product.country_external_id, 0) + 1
                )
            for attraction_link in product.attractions:
                key = attraction_link.attraction_external_id
                by_attraction[key] = by_attraction.get(key, 0) + 1
            for category_link in product.categories:
                key = category_link.category_external_id
                by_category[key] = by_category.get(key, 0) + 1
            for collection_link in product.collections:
                key = collection_link.collection_external_id
                by_collection[key] = by_collection.get(key, 0) + 1

        for city in self.session.scalars(select(City).where(City.market == market)):
            counted = by_city.get(city.external_id)
            if counted is not None:
                city.product_count = counted

        cities_by_country: dict[str, int] = {}
        for city in self.session.scalars(select(City).where(City.market == market)):
            if city.country_external_id:
                cities_by_country[city.country_external_id] = (
                    cities_by_country.get(city.country_external_id, 0) + 1
                )

        for country in self.session.scalars(select(Country).where(Country.market == market)):
            country.product_count = by_country.get(country.external_id, 0)
            country.city_count = cities_by_country.get(country.external_id, 0)

        for attraction in self.session.scalars(
            select(Attraction).where(Attraction.market == market)
        ):
            counted = by_attraction.get(attraction.external_id)
            if counted is not None:
                attraction.product_count = counted

        for category in self.session.scalars(select(Category).where(Category.market == market)):
            category.product_count = by_category.get(category.external_id, 0)

        for collection in self.session.scalars(
            select(Collection).where(Collection.market == market)
        ):
            collection.product_count = by_collection.get(collection.external_id, 0)

        self._recount_city_attractions(market)
        self.session.flush()

    def _recount_city_attractions(self, market: Market) -> None:
        counts: dict[str, int] = {}
        for attraction in self.session.scalars(
            select(Attraction).where(Attraction.market == market)
        ):
            if attraction.city_external_id:
                counts[attraction.city_external_id] = counts.get(attraction.city_external_id, 0) + 1
        for city in self.session.scalars(select(City).where(City.market == market)):
            city.attraction_count = counts.get(city.external_id, 0)

    # -------------------------------------------------------------- helpers
    def _find(self, model: Any, market: Market, external_id: str) -> Any:
        return self.session.scalar(
            select(model).where(model.market == market, model.external_id == external_id)
        )

    def _get_or_create(self, model: Any, market: Market, external_id: str) -> Any:
        row = self._find(model, market, external_id)
        if row is None:
            defaults: dict[str, Any] = {"market": market, "external_id": external_id, "slug": ""}
            columns = model.__table__.columns
            if "name" in columns:
                defaults["name"] = ""
            if "title" in columns:
                defaults["title"] = ""
            row = model(**defaults)
            self.session.add(row)
            self.session.flush()
        return row


def refresh_product(
    session: Session,
    provider: WeGoTripCatalogProvider,
    market: Market,
    external_id: str,
    *,
    settings: Settings | None = None,
) -> Product | None:
    """Re-read a single product from the API right before publication."""
    service = CatalogSyncService(session, provider, settings=settings)
    detail = provider.get_product(external_id, market)
    if detail is None:
        row = service._find(Product, market, external_id)
        if row is not None:
            row.available = False
        return row
    return service._upsert_product(detail, market, detail=True)


__all__ = ["CatalogSyncService", "SyncOptions", "SyncStats", "refresh_product", "snapshot_id"]
