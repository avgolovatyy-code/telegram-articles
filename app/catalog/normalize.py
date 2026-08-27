"""Raw Affiliate API payloads → normalized catalog entities.

Pure functions only: no HTTP, no database. Unknown/missing fields become ``None``
rather than guesses, and every entity keeps its raw payload for auditing.
"""

from __future__ import annotations

import re
from typing import Any

from slugify import slugify

from app.catalog.schemas import (
    MediaAsset,
    NormalizedAttraction,
    NormalizedCategory,
    NormalizedCity,
    NormalizedCollection,
    NormalizedCountry,
    NormalizedProduct,
    NormalizedReview,
    Page,
)
from app.config import Market
from app.errors import CatalogSchemaError

_PAGE_KEYS = {"results", "count", "pages", "current", "next"}
#: Keys observed in list payloads that carry aggregate data rather than pagination.
_PAGE_EXTRA_KEYS = {"maxPrice", "minPrice"}


def unwrap(payload: Any) -> Any:
    """v2 endpoints wrap everything in ``{"data": ...}``; v3 does not."""
    if isinstance(payload, dict) and "data" in payload and len(payload) <= 2:
        return payload["data"]
    return payload


def parse_page(payload: Any) -> Page:
    body = unwrap(payload)
    if isinstance(body, list):
        return Page(results=body, count=len(body), pages=1, current=1, next=None)
    if not isinstance(body, dict):
        raise CatalogSchemaError(f"Unexpected list payload type: {type(body).__name__}")
    results = body.get("results")
    if results is None:
        raise CatalogSchemaError("List payload has no 'results' key")
    if not isinstance(results, list):
        raise CatalogSchemaError("'results' is not a list")
    extra = {k: v for k, v in body.items() if k in _PAGE_EXTRA_KEYS}
    return Page(
        results=results,
        count=int(body.get("count") or len(results)),
        pages=int(body.get("pages") or 1),
        current=int(body.get("current") or 1),
        next=body.get("next"),
        extra=extra,
    )


def _str_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    return str(value)


def _slug_or_fallback(raw: dict[str, Any], name_key: str = "name") -> str:
    slug = raw.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    name = raw.get(name_key) or raw.get("title") or ""
    return slugify(str(name)) or "unknown"


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text") or item.get("title") or item.get("name")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    return out


# ------------------------------------------------------------------ entities
def normalize_country(
    raw: dict[str, Any], market: Market, *, rank: int | None = None
) -> NormalizedCountry:
    external_id = _str_id(raw.get("id"))
    if not external_id:
        raise CatalogSchemaError("Country payload has no id")
    return NormalizedCountry(
        external_id=external_id,
        slug=_slug_or_fallback(raw),
        name=str(raw.get("name") or raw.get("slug") or external_id),
        market=market,
        code=raw.get("code"),
        media=_media_from_preview(raw.get("preview")),
        product_count=_int_or_none(raw.get("itemsCount")) or 0,
        city_count=_int_or_none(raw.get("citiesCount")) or 0,
        popularity_rank=rank,
        raw=raw,
    )


def normalize_city(
    raw: dict[str, Any], market: Market, *, rank: int | None = None
) -> NormalizedCity:
    external_id = _str_id(raw.get("id"))
    if not external_id:
        raise CatalogSchemaError("City payload has no id")
    country = raw.get("country")
    country_id = None
    country_name = None
    if isinstance(country, dict):
        country_id = _str_id(country.get("id"))
        country_name = country.get("name")
    elif isinstance(country, str):
        country_name = country
    return NormalizedCity(
        external_id=external_id,
        slug=_slug_or_fallback(raw),
        name=str(raw.get("name") or external_id),
        market=market,
        country_external_id=country_id,
        country_name=country_name,
        popular=bool(raw.get("popular", rank is not None and rank < 50)),
        media=_media_from_preview(raw.get("preview")),
        product_count=_int_or_none(raw.get("itemsCount")) or 0,
        attraction_count=_int_or_none(raw.get("attractionsCount")) or 0,
        popularity_rank=rank,
        raw=raw,
    )


def normalize_attraction(
    raw: dict[str, Any],
    market: Market,
    *,
    city_external_id: str | None = None,
    country_external_id: str | None = None,
    rank: int | None = None,
) -> NormalizedAttraction:
    external_id = _str_id(raw.get("id"))
    if not external_id:
        raise CatalogSchemaError("Attraction payload has no id")
    city = raw.get("city")
    if isinstance(city, dict):
        city_external_id = _str_id(city.get("id")) or city_external_id
    preview = raw.get("preview")
    return NormalizedAttraction(
        external_id=external_id,
        slug=_slug_or_fallback(raw),
        name=str(raw.get("name") or external_id),
        market=market,
        city_external_id=city_external_id,
        country_external_id=country_external_id,
        preview=preview if isinstance(preview, str) else None,
        media=_media_from_preview(preview),
        product_count=_int_or_none(raw.get("itemsCount")) or 0,
        popularity_rank=rank,
        raw=raw,
    )


def normalize_category(raw: dict[str, Any], market: Market) -> NormalizedCategory:
    external_id = _str_id(raw.get("id"))
    title = str(raw.get("title") or raw.get("name") or "").strip()
    if not external_id:
        external_id = slugify(title) or "unknown"
    return NormalizedCategory(
        external_id=external_id,
        slug=_slug_or_fallback(raw, name_key="title"),
        title=title or external_id,
        market=market,
        raw=raw,
    )


def normalize_collection(raw: dict[str, Any], market: Market) -> NormalizedCollection:
    category = normalize_category(raw, market)
    return NormalizedCollection(
        external_id=category.external_id,
        slug=category.slug,
        title=category.title,
        market=market,
        source="subcategory",
        raw=raw,
    )


def _media_from_preview(preview: Any) -> list[MediaAsset]:
    if isinstance(preview, str) and preview.startswith("http"):
        return [MediaAsset(url=preview, preview_url=preview, is_cover=True)]
    return []


def _normalize_images(raw_images: Any) -> list[MediaAsset]:
    if not isinstance(raw_images, list):
        return []
    assets: list[MediaAsset] = []
    for position, item in enumerate(raw_images):
        if isinstance(item, str) and item.startswith("http"):
            assets.append(MediaAsset(url=item, position=position))
            continue
        if not isinstance(item, dict):
            continue
        url = item.get("full") or item.get("url") or item.get("preview")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        assets.append(
            MediaAsset(
                url=url,
                preview_url=item.get("preview") if isinstance(item.get("preview"), str) else None,
                description=item.get("description") or None,
                is_cover=bool(item.get("cover")),
                position=position,
            )
        )
    return assets


_DURATION_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _duration_bounds(raw: dict[str, Any]) -> tuple[int | None, int | None]:
    dmin = _int_or_none(raw.get("durationMin"))
    dmax = _int_or_none(raw.get("durationMax"))
    if dmin is not None or dmax is not None:
        return dmin, dmax
    return None, None


def normalize_product(
    raw: dict[str, Any],
    market: Market,
    *,
    rank: int | None = None,
    has_detail: bool = False,
) -> NormalizedProduct:
    external_id = _str_id(raw.get("id"))
    if not external_id:
        raise CatalogSchemaError("Product payload has no id")

    city = raw.get("city") if isinstance(raw.get("city"), dict) else {}
    country = raw.get("country") if isinstance(raw.get("country"), dict) else {}
    duration_min, duration_max = _duration_bounds(raw)

    categories = [
        normalize_category(item, market)
        for item in raw.get("categories", [])
        if isinstance(item, dict)
    ]
    collections = [
        normalize_collection(item, market)
        for item in raw.get("subcategories", [])
        if isinstance(item, dict)
    ]
    attractions = [
        normalize_attraction(item, market, city_external_id=_str_id(city.get("id")))
        for item in raw.get("attractions", [])
        if isinstance(item, dict)
    ]
    reviews = [
        NormalizedReview.model_validate(item)
        for item in raw.get("reviews", [])
        if isinstance(item, dict)
    ]

    tags = raw.get("tags") if isinstance(raw.get("tags"), dict) else {}
    types = raw.get("types") if isinstance(raw.get("types"), dict) else {}
    available = raw.get("available")
    if available is None:
        available = tags.get("available", True)

    return NormalizedProduct(
        external_id=external_id,
        slug=_slug_or_fallback(raw, name_key="title"),
        title=str(raw.get("title") or external_id),
        market=market,
        locale=raw.get("locale"),
        description=raw.get("description"),
        short_description=raw.get("shortDescription"),
        highlights=_str_list(raw.get("highlights")),
        cover=raw.get("cover") if isinstance(raw.get("cover"), str) else None,
        preview=raw.get("preview") if isinstance(raw.get("preview"), str) else None,
        images=_normalize_images(raw.get("images")),
        # The Affiliate API does not document an audio preview URL; see provider.py.
        audio_preview_url=raw.get("audioPreviewUrl")
        if isinstance(raw.get("audioPreviewUrl"), str)
        else None,
        price=_float_or_none(raw.get("price")),
        exprice=_float_or_none(raw.get("exprice")),
        currency_code=raw.get("currencyCode"),
        currency_symbol=raw.get("currency"),
        rating=_float_or_none(raw.get("rating")),
        reviews_count=_int_or_none(raw.get("reviewsCount")),
        ratings_count=_int_or_none(raw.get("ratingsCount")),
        duration_min=duration_min,
        duration_max=duration_max,
        duration_text=raw.get("duration") if isinstance(raw.get("duration"), str) else None,
        distance=raw.get("distance") if isinstance(raw.get("distance"), str) else None,
        available=bool(available),
        published=bool(raw.get("published", True)),
        types=types,
        tags=tags,
        inclusions=_str_list(raw.get("inclusions")),
        exclusions=_str_list(raw.get("exclusions")),
        important_info=_str_list(raw.get("importantInfo")),
        address=raw.get("address"),
        start_location=raw.get("startLocation"),
        location_geo=raw.get("locationGeo") if isinstance(raw.get("locationGeo"), dict) else None,
        country_external_id=_str_id(country.get("id")),
        country_name=country.get("name"),
        city_external_id=_str_id(city.get("id")),
        city_name=city.get("name"),
        city_slug=city.get("slug"),
        primary_category=raw.get("category") if isinstance(raw.get("category"), str) else None,
        categories=categories,
        collections=collections,
        attractions=attractions,
        reviews=reviews,
        canonical_url=raw.get("url") if isinstance(raw.get("url"), str) else None,
        popularity_rank=rank,
        api_updated_at=raw.get("lastModified") or raw.get("lastUpdatedByAuthor"),
        has_detail=has_detail,
        raw=raw,
    )


def merge_product(base: NormalizedProduct, detail: NormalizedProduct) -> NormalizedProduct:
    """Overlay a detail payload on a list payload, keeping list-only fields."""
    merged = detail.model_dump()
    fallback = base.model_dump()
    for key, value in fallback.items():
        if key in {"raw", "has_detail"}:
            continue
        current = merged.get(key)
        if current in (None, [], {}, ""):
            merged[key] = value
    merged["popularity_rank"] = (
        base.popularity_rank if base.popularity_rank is not None else detail.popularity_rank
    )
    merged["has_detail"] = True
    merged["raw"] = {**fallback.get("raw", {}), **detail.raw}
    return NormalizedProduct.model_validate(merged)


__all__ = [
    "merge_product",
    "normalize_attraction",
    "normalize_category",
    "normalize_city",
    "normalize_collection",
    "normalize_country",
    "normalize_product",
    "parse_page",
    "unwrap",
]
