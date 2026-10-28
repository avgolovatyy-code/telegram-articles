"""Live WeGoTrip Affiliate API adapter.

Endpoint versions were verified against the live API (2026-08):

===========================  =======  ==========================================
Endpoint                     Version  Notes
===========================  =======  ==========================================
``/currencies/``             v2       wrapped in ``data``
``/countries/``              v2       wrapped; no ``lang`` filter, honours header
``/cities/``                 v2       wrapped; ``lang`` changes names and counts
``/attractions/``            v2       wrapped; ``city``/``country`` filters work
``/products/popular/``       v2       wrapped; ``lang``/``city``/``attraction``
``/products/{id}/``          v2       wrapped; includes canonical ``url``
``/products/{id}/reviews/``  v2       wrapped
``/search/``                 v2       wrapped
``/languages/``              —        documented but returns 404; see below
``/attractions/`` (v3)       v3       unwrapped, but ignores the ``city`` filter
===========================  =======  ==========================================

Known gaps (documented, not invented):

* ``/languages/`` is 404 on both v2 and v3 → :meth:`get_languages` falls back to the
  configured market list.
* There is no ``/categories/`` or ``/collections/`` endpoint → categories and
  collections are derived from product details (``categories`` / ``subcategories``).
* No product audio preview URL is exposed → see ``AudioPreviewProvider``.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.catalog.http import RateLimiter, request_with_retries
from app.catalog.normalize import (
    normalize_attraction,
    normalize_city,
    normalize_country,
    normalize_product,
    parse_page,
    unwrap,
)
from app.catalog.schemas import (
    NormalizedAttraction,
    NormalizedCity,
    NormalizedCountry,
    NormalizedProduct,
    Page,
)
from app.config import MARKETS, Market, Settings, get_settings
from app.errors import CatalogError
from app.logging_setup import get_logger

log = get_logger("catalog.wegotrip")

MAX_PAGES_HARD_LIMIT = 500


class WeGoTripHttpProvider:
    """HTTP implementation of :class:`~app.catalog.provider.WeGoTripCatalogProvider`."""

    name = "http"

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self._settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(self._settings.wegotrip_timeout_seconds),
            headers={"User-Agent": "WeGoTripContentEngine/0.1 (+https://wegotrip.com)"},
            follow_redirects=True,
        )
        self._limiter = RateLimiter(self._settings.wegotrip_rate_limit_rps)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> WeGoTripHttpProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -------------------------------------------------------------- requests
    def _url(self, path: str, version: str, *, market: Market | None = None) -> str:
        if market is not None:
            base = self._settings.api_base_url(market)
        else:
            base = self._settings.wegotrip_api_base_url.rstrip("/")
        return f"{base}/{version}/{path.strip('/')}/"

    def _get(
        self,
        path: str,
        *,
        version: str = "v2",
        market: Market | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers: dict[str, str] = {}
        if market:
            headers["Accept-Language"] = market
            # Match the storefront host so CDN/geo routing stays consistent.
            headers["Origin"] = f"https://{self._settings.store_domain(market)}"
            headers["Referer"] = f"https://{self._settings.store_domain(market)}/"
        if self._settings.wegotrip_api_key:
            headers["Authorization"] = f"Bearer {self._settings.wegotrip_api_key}"

        url = self._url(path, version, market=market)
        response = request_with_retries(
            self._client,
            "GET",
            url,
            params=params,
            headers=headers,
            max_retries=self._settings.wegotrip_max_retries,
            limiter=self._limiter,
            error_cls=CatalogError,
        )
        if response.status_code == 404:
            raise CatalogError(f"Endpoint not available: {url}", status_code=404)
        if response.status_code >= 400:
            raise CatalogError(
                f"WeGoTrip API {response.status_code} for {url}",
                status_code=response.status_code,
                payload=response.text[:500],
            )
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            raise CatalogError(f"Non-JSON response from {url} ({content_type})")
        return response.json()

    def _paginate(
        self,
        path: str,
        *,
        version: str = "v2",
        market: Market | None = None,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        page_number = 1
        total_pages = 1
        while page_number <= min(total_pages, max_pages or MAX_PAGES_HARD_LIMIT):
            payload = self._get(
                path, version=version, market=market, params={**(params or {}), "page": page_number}
            )
            page: Page = parse_page(payload)
            total_pages = max(total_pages, page.pages)
            collected.extend(page.results)
            if max_items is not None and len(collected) >= max_items:
                return collected[:max_items]
            if page.next is None:
                break
            page_number += 1
        return collected

    # -------------------------------------------------------------- entities
    def get_languages(self) -> list[dict[str, str]]:
        """``/languages/`` is 404 on the live API; fall back to the configured markets."""
        try:
            payload = unwrap(self._get("languages", version="v2"))
        except CatalogError as exc:
            log.info("catalog.languages_unavailable", reason=str(exc))
            return [{"code": market, "source": "configured"} for market in MARKETS]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return [{"code": market, "source": "configured"} for market in MARKETS]

    def get_currencies(self) -> list[dict[str, object]]:
        payload = unwrap(self._get("currencies", version="v2"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def get_countries(self, market: Market) -> list[NormalizedCountry]:
        rows = self._paginate("countries", market=market, params={"lang": market})
        return [normalize_country(row, market, rank=i) for i, row in enumerate(rows)]

    def get_cities(
        self, market: Market, *, country_id: str | None = None, popular: bool = True
    ) -> list[NormalizedCity]:
        rows = self._paginate(
            "cities",
            market=market,
            params={"lang": market, "country": country_id, "popular": str(popular).lower()},
        )
        return [normalize_city(row, market, rank=i) for i, row in enumerate(rows)]

    def get_attractions(
        self, market: Market, *, city_id: str | None = None, country_id: str | None = None
    ) -> list[NormalizedAttraction]:
        rows = self._paginate(
            "attractions",
            market=market,
            params={"lang": market, "city": city_id, "country": country_id},
        )
        return [
            normalize_attraction(
                row, market, city_external_id=city_id, country_external_id=country_id, rank=i
            )
            for i, row in enumerate(rows)
        ]

    def get_products(
        self,
        market: Market,
        *,
        city_id: str | None = None,
        country_id: str | None = None,
        attraction_id: str | None = None,
        max_items: int | None = None,
    ) -> list[NormalizedProduct]:
        rows = self._paginate(
            "products/popular",
            market=market,
            params={
                "lang": market,
                "currency": self._settings.currency(market),
                "city": city_id,
                "country": country_id,
                "attraction": attraction_id,
                "order": "popularity",
            },
            max_items=max_items,
        )
        return [normalize_product(row, market, rank=i) for i, row in enumerate(rows)]

    def get_product(self, product_id: str, market: Market) -> NormalizedProduct | None:
        try:
            payload = unwrap(
                self._get(
                    f"products/{product_id}",
                    market=market,
                    params={"currency": self._settings.currency(market)},
                )
            )
        except CatalogError as exc:
            if exc.status_code == 404:
                return None
            raise
        if not isinstance(payload, dict):
            return None
        return normalize_product(payload, market, has_detail=True)

    def get_product_reviews(self, product_id: str, market: Market) -> list[dict[str, object]]:
        rows = self._paginate(f"products/{product_id}/reviews", market=market, max_pages=2)
        return list(rows)

    def search(self, query: str, market: Market) -> dict[str, object]:
        payload = unwrap(
            self._get(
                "search",
                market=market,
                params={"query": query, "currency": self._settings.currency(market)},
            )
        )
        return payload if isinstance(payload, dict) else {}


__all__ = ["WeGoTripHttpProvider"]
