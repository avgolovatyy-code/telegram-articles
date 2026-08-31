"""Offline catalog provider backed by fixtures captured from the live API.

Enable with ``CATALOG_PROVIDER=mock``. The fixtures are real (unmodified) Affiliate API
payloads captured by ``scripts/capture_fixtures.py``, so normalization is exercised
against the actual schema rather than an idealised one.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.catalog.normalize import (
    normalize_attraction,
    normalize_city,
    normalize_country,
    normalize_product,
)
from app.catalog.schemas import (
    NormalizedAttraction,
    NormalizedCity,
    NormalizedCountry,
    NormalizedProduct,
)
from app.config import MARKETS, Market

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@lru_cache(maxsize=4)
def _load(name: str) -> Any:
    path = FIXTURES_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class MockCatalogProvider:
    """Fixture-backed implementation of ``WeGoTripCatalogProvider``."""

    name = "mock"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._dir = fixtures_dir or FIXTURES_DIR

    def _market_data(self, market: Market) -> dict[str, Any]:
        if self._dir == FIXTURES_DIR:
            data = _load(f"catalog_{market}.json")
        else:
            path = self._dir / f"catalog_{market}.json"
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return data if isinstance(data, dict) else {}

    # -------------------------------------------------------------- protocol
    def get_languages(self) -> list[dict[str, str]]:
        return [{"code": market, "source": "fixture"} for market in MARKETS]

    def get_currencies(self) -> list[dict[str, object]]:
        data = _load("currencies.json") if self._dir == FIXTURES_DIR else []
        return data if isinstance(data, list) else []

    def get_countries(self, market: Market) -> list[NormalizedCountry]:
        rows = self._market_data(market).get("countries", [])
        return [normalize_country(row, market, rank=i) for i, row in enumerate(rows)]

    def get_cities(
        self, market: Market, *, country_id: str | None = None, popular: bool = True
    ) -> list[NormalizedCity]:
        rows = self._market_data(market).get("cities", [])
        cities = [normalize_city(row, market, rank=i) for i, row in enumerate(rows)]
        if country_id:
            cities = [c for c in cities if c.country_external_id == country_id]
        return cities

    def get_attractions(
        self, market: Market, *, city_id: str | None = None, country_id: str | None = None
    ) -> list[NormalizedAttraction]:
        data = self._market_data(market)
        rows = data.get("attractions", [])
        selected = data.get("selected_city_ids", [])
        attractions: list[NormalizedAttraction] = []
        per_city = len(rows) // max(len(selected), 1) if selected else len(rows)
        for index, row in enumerate(rows):
            owner = selected[index // per_city] if selected and per_city else city_id
            attractions.append(
                normalize_attraction(row, market, city_external_id=owner, rank=index)
            )
        if city_id:
            attractions = [a for a in attractions if a.city_external_id == city_id]
        return attractions

    def get_products(
        self,
        market: Market,
        *,
        city_id: str | None = None,
        country_id: str | None = None,
        attraction_id: str | None = None,
        max_items: int | None = None,
    ) -> list[NormalizedProduct]:
        rows = self._market_data(market).get("products", [])
        products = [normalize_product(row, market, rank=i) for i, row in enumerate(rows)]
        if city_id:
            products = [p for p in products if p.city_external_id == city_id]
        if country_id:
            products = [p for p in products if p.country_external_id == country_id]
        if attraction_id:
            products = [
                p for p in products if any(a.external_id == attraction_id for a in p.attractions)
            ]
        return products[:max_items] if max_items else products

    def get_product(self, product_id: str, market: Market) -> NormalizedProduct | None:
        details = self._market_data(market).get("product_details", {})
        raw = details.get(str(product_id))
        if raw is None:
            return None
        return normalize_product(raw, market, has_detail=True)

    def get_product_reviews(self, product_id: str, market: Market) -> list[dict[str, object]]:
        product = self.get_product(product_id, market)
        if product is None:
            return []
        return [review.model_dump() for review in product.reviews]

    def search(self, query: str, market: Market) -> dict[str, object]:
        lowered = query.lower()
        data = self._market_data(market)
        return {
            "cities": [
                c for c in data.get("cities", []) if lowered in str(c.get("name", "")).lower()
            ],
            "products": [
                p for p in data.get("products", []) if lowered in str(p.get("title", "")).lower()
            ],
        }


__all__ = ["FIXTURES_DIR", "MockCatalogProvider"]
