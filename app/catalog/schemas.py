"""Normalized catalog entities.

These models are the boundary between the raw Affiliate API payloads and the rest of
the engine. Fields the API does not return stay ``None`` — they are never invented.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.config import Market


class MediaAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    preview_url: str | None = None
    kind: str = "photo"
    description: str | None = None
    is_cover: bool = False
    position: int = 0


class NormalizedCountry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    slug: str
    name: str
    market: Market
    code: str | None = None
    media: list[MediaAsset] = Field(default_factory=list)
    product_count: int = 0
    city_count: int = 0
    popularity_rank: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedCity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    slug: str
    name: str
    market: Market
    country_external_id: str | None = None
    country_name: str | None = None
    popular: bool = False
    media: list[MediaAsset] = Field(default_factory=list)
    product_count: int = 0
    attraction_count: int = 0
    popularity_rank: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedAttraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    slug: str
    name: str
    market: Market
    city_external_id: str | None = None
    country_external_id: str | None = None
    preview: str | None = None
    media: list[MediaAsset] = Field(default_factory=list)
    product_count: int = 0
    popularity_rank: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    slug: str
    title: str
    market: Market
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedCollection(BaseModel):
    """A collection is a normalized ``subcategory`` from product details."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    slug: str
    title: str
    market: Market
    source: str = "subcategory"
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedReview(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    text: str | None = None
    rating: float | None = None
    date: str | None = None


class NormalizedProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str
    slug: str
    title: str
    market: Market
    locale: str | None = None

    description: str | None = None
    short_description: str | None = None
    highlights: list[str] = Field(default_factory=list)

    cover: str | None = None
    preview: str | None = None
    images: list[MediaAsset] = Field(default_factory=list)
    #: Only ever set when the API returns a real, playable preview URL (spec §29).
    audio_preview_url: str | None = None

    price: float | None = None
    exprice: float | None = None
    currency_code: str | None = None
    currency_symbol: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    ratings_count: int | None = None
    duration_min: int | None = None
    duration_max: int | None = None
    duration_text: str | None = None
    distance: str | None = None

    available: bool = True
    published: bool = True
    types: dict[str, Any] = Field(default_factory=dict)
    tags: dict[str, Any] = Field(default_factory=dict)
    inclusions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    important_info: list[str] = Field(default_factory=list)
    address: str | None = None
    start_location: str | None = None
    location_geo: dict[str, Any] | None = None

    country_external_id: str | None = None
    country_name: str | None = None
    city_external_id: str | None = None
    city_name: str | None = None
    city_slug: str | None = None
    primary_category: str | None = None

    categories: list[NormalizedCategory] = Field(default_factory=list)
    collections: list[NormalizedCollection] = Field(default_factory=list)
    attractions: list[NormalizedAttraction] = Field(default_factory=list)
    reviews: list[NormalizedReview] = Field(default_factory=list)

    canonical_url: str | None = None
    popularity_rank: int | None = None
    api_updated_at: str | None = None
    has_detail: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def media(self) -> list[MediaAsset]:
        assets: list[MediaAsset] = []
        seen: set[str] = set()
        if self.cover:
            assets.append(MediaAsset(url=self.cover, preview_url=self.preview, is_cover=True))
            seen.add(self.cover)
        for image in self.images:
            if image.url in seen:
                continue
            seen.add(image.url)
            assets.append(image)
        return assets


class Page(BaseModel):
    """One page of a paginated Affiliate API list response."""

    model_config = ConfigDict(extra="forbid")

    results: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    pages: int = 1
    current: int = 1
    next: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "MediaAsset",
    "NormalizedAttraction",
    "NormalizedCategory",
    "NormalizedCity",
    "NormalizedCollection",
    "NormalizedCountry",
    "NormalizedProduct",
    "NormalizedReview",
    "Page",
]
