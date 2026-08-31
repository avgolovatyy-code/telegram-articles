#!/usr/bin/env python3
"""Capture a small, realistic slice of the live Affiliate API into fixtures.

The fixtures back ``CATALOG_PROVIDER=mock`` so the whole pipeline can be developed
and tested without network access. Re-run when the upstream schema changes:

    python scripts/capture_fixtures.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
from typing import Any

import httpx

BASE = "https://app.wegotrip.com/api"
OUT = pathlib.Path(__file__).resolve().parents[1] / "app" / "catalog" / "fixtures"

# EN: Paris (a deep, well-known catalogue). RU: Saint Petersburg, resolved at runtime.
EN_CITY_HINTS = ["Paris", "Rome"]
RU_CITY_HINTS = ["Санкт-Петербург", "Москва"]
PRODUCTS_PER_CITY = 12
DETAILS_PER_CITY = 6


def get(client: httpx.Client, path: str, market: str, **params: Any) -> Any:
    response = client.get(
        f"{BASE}/{path}",
        params={k: v for k, v in params.items() if v is not None},
        headers={"Accept-Language": market},
        timeout=60,
    )
    response.raise_for_status()
    time.sleep(0.2)
    return response.json()


def unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def pick_cities(cities: list[dict[str, Any]], hints: list[str], limit: int) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for hint in hints:
        for city in cities:
            if city.get("name") == hint and city not in chosen:
                chosen.append(city)
    for city in cities:
        if len(chosen) >= limit:
            break
        if city not in chosen:
            chosen.append(city)
    return chosen[:limit]


def capture_market(client: httpx.Client, market: str, hints: list[str]) -> dict[str, Any]:
    countries = unwrap(get(client, "v2/countries/", market, lang=market))["results"]
    cities = unwrap(get(client, "v2/cities/", market, lang=market))["results"]
    selected = pick_cities(cities, hints, 2)

    attractions: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    details: dict[str, Any] = {}

    for city in selected:
        city_id = city["id"]
        attr = unwrap(get(client, "v2/attractions/", market, lang=market, city=city_id))
        attractions.extend(attr["results"][:12])

        prods = unwrap(
            get(
                client,
                "v2/products/popular/",
                market,
                lang=market,
                city=city_id,
                currency="RUB" if market == "ru" else "EUR",
            )
        )
        page = prods["results"][:PRODUCTS_PER_CITY]
        products.extend(page)
        for product in page[:DETAILS_PER_CITY]:
            detail = unwrap(
                get(
                    client,
                    f"v2/products/{product['id']}/",
                    market,
                    currency="RUB" if market == "ru" else "EUR",
                )
            )
            detail.pop("tickets", None)
            detail["reviews"] = detail.get("reviews", [])[:2]
            details[str(product["id"])] = detail

    return {
        "market": market,
        "countries": countries[:40],
        "cities": list(cities[:40]),
        "selected_city_ids": [str(c["id"]) for c in selected],
        "attractions": attractions,
        "products": products,
        "product_details": details,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True) as client:
        currencies = unwrap(get(client, "v2/currencies/", "en"))
        (OUT / "currencies.json").write_text(
            json.dumps(currencies, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        for market, hints in (("en", EN_CITY_HINTS), ("ru", RU_CITY_HINTS)):
            data = capture_market(client, market, hints)
            (OUT / f"catalog_{market}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(
                f"{market}: {len(data['cities'])} cities, {len(data['attractions'])} attractions, "
                f"{len(data['products'])} products, {len(data['product_details'])} details"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
