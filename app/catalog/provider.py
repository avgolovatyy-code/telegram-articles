"""Provider interfaces for external catalog data.

`WeGoTripCatalogProvider` is the only contract the rest of the engine knows about;
`WeGoTripHttpProvider` (live API) and `MockCatalogProvider` (offline fixtures)
implement it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from app.catalog.schemas import (
    NormalizedAttraction,
    NormalizedCity,
    NormalizedCountry,
    NormalizedProduct,
)
from app.config import Market


@runtime_checkable
class WeGoTripCatalogProvider(Protocol):
    """Read access to the WeGoTrip catalogue for a single market at a time."""

    def get_languages(self) -> list[dict[str, str]]:
        """Supported content languages.

        The documented ``/languages/`` endpoint currently returns 404 on the live API,
        so implementations may fall back to the configured market list.
        """

    def get_currencies(self) -> list[dict[str, object]]: ...

    def get_countries(self, market: Market) -> list[NormalizedCountry]: ...

    def get_cities(
        self, market: Market, *, country_id: str | None = None, popular: bool = True
    ) -> list[NormalizedCity]: ...

    def get_attractions(
        self, market: Market, *, city_id: str | None = None, country_id: str | None = None
    ) -> list[NormalizedAttraction]: ...

    def get_products(
        self,
        market: Market,
        *,
        city_id: str | None = None,
        country_id: str | None = None,
        attraction_id: str | None = None,
        max_items: int | None = None,
    ) -> list[NormalizedProduct]: ...

    def get_product(self, product_id: str, market: Market) -> NormalizedProduct | None: ...

    def get_product_reviews(self, product_id: str, market: Market) -> list[dict[str, object]]: ...

    def search(self, query: str, market: Market) -> dict[str, object]: ...


@runtime_checkable
class AudioPreviewProvider(Protocol):
    """Resolves a playable audio preview for a product.

    The documented Affiliate API exposes audio-guide *metadata* (``types.audioguide``,
    ``tour.mediaSize``, ``tour.eventsCount``) but no preview URL. The default
    implementation therefore returns ``None`` for everything; a future provider can be
    dropped in without touching the renderer.
    """

    def get_audio_preview(self, product: NormalizedProduct) -> str | None: ...


class NullAudioPreviewProvider:
    """Default: the Affiliate API does not publish audio preview URLs."""

    name = "null"

    def get_audio_preview(self, product: NormalizedProduct) -> str | None:
        return None


class StaticAudioPreviewProvider:
    """Serves audio previews from an explicit ``{product_id: url}`` mapping."""

    name = "static"

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._mapping = dict(mapping or {})

    def add(self, product_id: str, url: str) -> None:
        self._mapping[str(product_id)] = url

    def get_audio_preview(self, product: NormalizedProduct) -> str | None:
        return self._mapping.get(str(product.external_id))


@runtime_checkable
class CollectionProvider(Protocol):
    """Dedicated Collections source.

    The Affiliate API has no ``/collections/`` endpoint today, so collections are
    derived from product ``subcategories``. This interface exists so a real endpoint
    can be wired in later without touching topic discovery.
    """

    def get_collections(self, market: Market) -> Iterable[object]: ...


__all__ = [
    "AudioPreviewProvider",
    "CollectionProvider",
    "NullAudioPreviewProvider",
    "StaticAudioPreviewProvider",
    "WeGoTripCatalogProvider",
]
