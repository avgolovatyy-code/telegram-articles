"""Match 0–3 locale=ru WeGoTrip products to a Dzen brief."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import City, Product
from app.dzen.links import image_url_is_clean, product_affiliate_url


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


def _ticket_included(product: Product) -> bool | None:
    blob = " ".join(product.inclusions or []).casefold()
    if not blob:
        return None
    return "билет" in blob or "вход" in blob or "ticket" in blob


def match_products(
    session: Session,
    *,
    article_id: str,
    topic_slug: str | None,
    city_name: str | None,
    country_code: str | None,
    limit: int = 3,
    settings: Settings | None = None,
) -> list[DzenProductPick]:
    settings = settings or get_settings()
    query = select(Product).where(
        Product.market == "ru",
        Product.available.is_(True),
        Product.published.is_(True),
        or_(Product.locale.is_(None), Product.locale.in_(["ru", "RU"])),
    )
    products = list(session.scalars(query).all())
    city_fold = (city_name or "").casefold()
    scored: list[tuple[int, Product]] = []
    for product in products:
        score = 0
        city = None
        if product.city_external_id:
            city = session.scalar(
                select(City).where(
                    City.market == "ru", City.external_id == product.city_external_id
                )
            )
        hay = " ".join(
            part
            for part in (
                product.title,
                product.primary_category,
                city.name if city else "",
            )
            if part
        ).casefold()
        if city_fold and city_fold in hay:
            score += 5
        if country_code and (product.country_external_id or "").upper() == country_code.upper():
            score += 2
        if product.cover and image_url_is_clean(product.cover):
            score += 1
        if score:
            scored.append((score, product))
    scored.sort(key=lambda item: (-item[0], item[1].popularity_rank or 10_000))
    picks: list[DzenProductPick] = []
    for _, product in scored[:limit]:
        city = None
        if product.city_external_id:
            city = session.scalar(
                select(City).where(
                    City.market == "ru", City.external_id == product.city_external_id
                )
            )
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
                snapshot={
                    "title": product.title,
                    "price": product.price,
                    "currency": product.currency_code,
                    "inclusions": product.inclusions,
                    "exclusions": product.exclusions,
                },
            )
        )
    return picks


__all__ = ["DzenProductPick", "match_products"]
