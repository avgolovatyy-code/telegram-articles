"""Match 0–3 locale=ru WeGoTrip products to places actually named in the article.

Nearby cities (Sviyazhsk for a Kazan weekend, Peterhof for Petersburg) are not
added just because they share a catalog city id. Zero products is a valid outcome.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import City, Product, ProductAttraction
from app.dzen.links import image_url_is_clean, product_affiliate_url

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
PLACE_TOKEN = re.compile(r"[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё-]{3,}")
GENERIC_TOKENS = {
    "билет",
    "билета",
    "входной",
    "вход",
    "аудиоэкскурсия",
    "аудиогид",
    "аудиотур",
    "квиз",
    "приложение",
    "обзорная",
    "комплексный",
    "прогулка",
    "экскурсия",
    "музей",
    "музея",
    "тур",
    "туры",
    "час",
    "часа",
    "главным",
    "шедеврам",
    "без",
    "очереди",
    "островом",
    "острову",
    "граду",
    "городские",
    "легенды",
    "we go",
    "wegotrip",
}
MIN_KEEP_SCORE = 8


@dataclass(slots=True)
class DzenProductPick:
    external_id: str
    title: str
    slug: str
    affiliate_url: str
    inclusions: list[str]
    exclusions: list[str]
    ticket_included: bool | None
    cover: str | None
    city_name: str | None
    snapshot: dict[str, Any]
    score: int = 0
    matched_places: list[str] | None = None


def fold_place(word: str) -> str:
    token = (word or "").casefold().replace("ё", "е").replace("ь", "").replace("ъ", "")
    for suffix in ("ого", "ему", "ами", "ях", "ой", "ая", "ии", "ий", "ый", "ов", "ев"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    for suffix in ("а", "я", "у", "е", "и", "ы", "ю"):
        if len(token) > 4 and token.endswith(suffix):
            return token[:-1]
    return token


def looks_russian(text: str) -> bool:
    return len(CYRILLIC.findall(text or "")) >= 3


def place_tokens(*parts: str | None) -> set[str]:
    found: set[str] = set()
    for part in parts:
        for raw in PLACE_TOKEN.findall(part or ""):
            if raw.casefold() in GENERIC_TOKENS:
                continue
            folded = fold_place(raw)
            if len(folded) < 4 or folded in GENERIC_TOKENS:
                continue
            found.add(folded)
    return found


def _ticket_included(product: Product) -> bool | None:
    blob = " ".join(product.inclusions or []).casefold()
    if not blob:
        return None
    return "билет" in blob or "вход" in blob or "ticket" in blob


def _city_for(session: Session, product: Product) -> City | None:
    if not product.city_external_id:
        return None
    return session.scalar(
        select(City).where(City.market == "ru", City.external_id == product.city_external_id)
    )


def _destination_city(session: Session, city_name: str | None) -> City | None:
    if not city_name:
        return None
    wanted = fold_place(city_name)
    cities = list(session.scalars(select(City).where(City.market == "ru")))
    exact = [city for city in cities if fold_place(city.name) == wanted]
    if len(exact) > 1:
        ru = [
            city for city in exact if (city.country_name or "").casefold() in {"russia", "россия"}
        ]
        exact = ru or exact
    if exact:
        return exact[0]
    folded_query = city_name.casefold()
    for city in cities:
        if city.slug and folded_query == city.slug.casefold():
            return city
    return None


def _attraction_names(product: Product) -> list[str]:
    names: list[str] = []
    for item in product.attractions or []:
        if isinstance(item, ProductAttraction) and item.name:
            names.append(item.name)
    return names


def score_product(
    product: Product,
    *,
    article_tokens: set[str],
    destination: City | None,
    city: City | None,
) -> tuple[int, list[str]]:
    if not product.available or not product.published:
        return 0, []
    if not looks_russian(product.title or ""):
        return 0, []
    locale = (product.locale or "").lower()
    if locale and locale not in {"ru", "ru-ru"}:
        return 0, []

    title_tokens = place_tokens(product.title)
    hay_tokens = title_tokens | place_tokens(
        product.description,
        product.short_description,
        city.name if city else "",
        *_attraction_names(product),
    )
    dest_token = fold_place(destination.name) if destination else ""
    # Only the product title / attraction names may hard-reject: a Kazan tour
    # whose long description mentions a nearby island must still be eligible.
    distinctive = title_tokens - ({dest_token} if dest_token else set())
    unmatched = distinctive - article_tokens
    if unmatched:
        return 0, []

    score = 0
    matched: list[str] = []
    same_city = bool(
        destination
        and city
        and (
            city.external_id == destination.external_id
            or fold_place(city.name) == fold_place(destination.name)
        )
    )
    # A named destination city is a hard filter: mentioning another city in
    # passing must not attach that city's catalogue (SPb beer on a Kazan weekend).
    if destination is not None and not same_city:
        return 0, []
    if same_city:
        score += 8
        matched.append(city.name if city else "city")
    overlap = hay_tokens & article_tokens
    if overlap:
        score += 4 * min(3, len(overlap))
        matched.extend(sorted(overlap))
    if not same_city and not overlap:
        return 0, []
    if score < MIN_KEEP_SCORE and not overlap:
        return 0, []
    return score, matched


def match_products(
    session: Session,
    *,
    article_id: str,
    topic_slug: str | None,
    city_name: str | None,
    country_code: str | None,
    article_text: str | None = None,
    limit: int = 3,
    settings: Settings | None = None,
) -> list[DzenProductPick]:
    settings = settings or get_settings()
    destination = _destination_city(session, city_name)
    article_tokens = place_tokens(article_text or "", city_name)
    query = select(Product).where(
        Product.market == "ru",
        Product.available.is_(True),
        Product.published.is_(True),
        or_(Product.locale.is_(None), Product.locale.in_(["ru", "RU"])),
    )
    scored: list[tuple[int, list[str], Product, City | None]] = []
    for product in session.scalars(query):
        city = _city_for(session, product)
        score, matched = score_product(
            product,
            article_tokens=article_tokens,
            destination=destination,
            city=city,
        )
        if score >= MIN_KEEP_SCORE:
            scored.append((score, matched, product, city))
    scored.sort(key=lambda item: (-item[0], item[2].popularity_rank or 10_000))

    picks: list[DzenProductPick] = []
    seen_titles: set[str] = set()
    for score, matched, product, city in scored:
        title_key = fold_place(product.title)
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        url = product_affiliate_url(
            canonical_url=product.canonical_url,
            product_slug=product.slug,
            product_id=product.external_id,
            article_id=article_id,
            topic_slug=topic_slug,
            city_slug=city.slug if city else None,
            city_id=city.external_id if city else None,
            settings=settings,
        )
        picks.append(
            DzenProductPick(
                external_id=product.external_id,
                title=product.title,
                slug=product.slug,
                affiliate_url=url,
                inclusions=list(product.inclusions or []),
                exclusions=list(product.exclusions or []),
                ticket_included=_ticket_included(product),
                cover=product.cover
                if product.cover and image_url_is_clean(product.cover)
                else None,
                city_name=city.name if city else None,
                score=score,
                matched_places=matched,
                snapshot={
                    "title": product.title,
                    "price": product.price,
                    "currency": product.currency_code,
                    "inclusions": product.inclusions,
                    "exclusions": product.exclusions,
                    "score": score,
                    "matched_places": matched,
                },
            )
        )
        if len(picks) >= max(0, min(3, limit)):
            break
    return picks


__all__ = [
    "DzenProductPick",
    "fold_place",
    "looks_russian",
    "match_products",
    "place_tokens",
    "score_product",
]
