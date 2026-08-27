"""Catalog integration package."""

from __future__ import annotations

from app.catalog.mock import MockCatalogProvider
from app.catalog.provider import (
    AudioPreviewProvider,
    NullAudioPreviewProvider,
    StaticAudioPreviewProvider,
    WeGoTripCatalogProvider,
)
from app.catalog.wegotrip import WeGoTripHttpProvider
from app.config import Settings, get_settings


def build_catalog_provider(settings: Settings | None = None) -> WeGoTripCatalogProvider:
    settings = settings or get_settings()
    if settings.catalog_provider == "mock":
        return MockCatalogProvider()
    return WeGoTripHttpProvider(settings)


def build_audio_preview_provider(settings: Settings | None = None) -> AudioPreviewProvider:
    """The Affiliate API exposes no audio preview URL, so the null provider is default."""
    _ = settings
    return NullAudioPreviewProvider()


__all__ = [
    "AudioPreviewProvider",
    "MockCatalogProvider",
    "NullAudioPreviewProvider",
    "StaticAudioPreviewProvider",
    "WeGoTripCatalogProvider",
    "WeGoTripHttpProvider",
    "build_audio_preview_provider",
    "build_catalog_provider",
]
