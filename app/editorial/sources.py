"""Curated SourceRegistry (spec §7). Legal primary URLs only — no scraping here."""

from __future__ import annotations

from typing import Any

from app.config import Market

#: Trust tiers: A official operator, B established media, C secondary.
SOURCE_REGISTRY: dict[str, list[dict[str, Any]]] = {
    "ru": [
        {
            "id": "hermitage",
            "name": "Государственный Эрмитаж",
            "url": "https://www.hermitagemuseum.org/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "tretyakov",
            "name": "Третьяковская галерея",
            "url": "https://www.tretyakovgallery.ru/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "pushkin_museum",
            "name": "ГМИИ им. А. С. Пушкина",
            "url": "https://pushkinmuseum.art/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "moscow_kremlin",
            "name": "Музеи Московского Кремля",
            "url": "https://www.kreml.ru/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "erarta",
            "name": "Эрарта",
            "url": "https://www.erarta.com/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "russpass",
            "name": "RUSSPASS",
            "url": "https://russpass.ru/",
            "tier": "A",
            "kind": "official_tourism",
        },
        {
            "id": "culture_rf",
            "name": "Культура.РФ",
            "url": "https://www.culture.ru/",
            "tier": "A",
            "kind": "official_culture",
        },
        {
            "id": "moscow_mayor",
            "name": "Мосгортур / mos.ru",
            "url": "https://www.mos.ru/",
            "tier": "A",
            "kind": "city",
        },
    ],
    "en": [
        {
            "id": "louvre",
            "name": "Musée du Louvre",
            "url": "https://www.louvre.fr/en",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "british_museum",
            "name": "The British Museum",
            "url": "https://www.britishmuseum.org/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "met",
            "name": "The Metropolitan Museum of Art",
            "url": "https://www.metmuseum.org/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "rijksmuseum",
            "name": "Rijksmuseum",
            "url": "https://www.rijksmuseum.nl/en",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "uffizi",
            "name": "Uffizi Galleries",
            "url": "https://www.uffizi.it/en",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "vatican",
            "name": "Vatican Museums",
            "url": "https://www.museivaticani.va/",
            "tier": "A",
            "kind": "museum",
        },
        {
            "id": "visitbritain",
            "name": "VisitBritain",
            "url": "https://www.visitbritain.com/",
            "tier": "A",
            "kind": "official_tourism",
        },
        {
            "id": "nyc_gov",
            "name": "NYC Official Guide",
            "url": "https://www.nyc.gov/visiting",
            "tier": "A",
            "kind": "city",
        },
    ],
}


def sources_for_market(market: Market) -> list[dict[str, Any]]:
    return list(SOURCE_REGISTRY.get(market, []))


__all__ = ["SOURCE_REGISTRY", "sources_for_market"]
