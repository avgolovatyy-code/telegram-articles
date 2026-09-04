"""Geography helpers for topic selection (Russia preference, city keys)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market
from app.db.enums import EntityType
from app.db.models import Attraction, City, Country, Product, TopicCandidate

RUSSIA_COUNTRY_CODES = frozenset({"RU"})
RUSSIA_COUNTRY_NAMES = frozenset(
    {
        "russia",
        "россия",
        "russian federation",
        "российская федерация",
    }
)


@dataclass(slots=True, frozen=True)
class TopicGeo:
    country_id: str | None
    city_id: str | None
    attraction_id: str | None
    is_russia: bool


def is_russia_country(*, code: str | None = None, name: str | None = None) -> bool:
    if code and code.upper() in RUSSIA_COUNTRY_CODES:
        return True
    return bool(name and name.casefold() in RUSSIA_COUNTRY_NAMES)


def _city_id_from_compound(external_id: str) -> str | None:
    # category/collection keys look like "{id}@{city_id}"
    if "@" in external_id:
        _, _, city = external_id.partition("@")
        return city or None
    return None


class GeoResolver:
    """Resolve country/city/attraction for topics and articles from the catalogue."""

    def __init__(self, session: Session, market: Market) -> None:
        self.session = session
        self.market = market
        self._countries = {
            c.external_id: c
            for c in session.scalars(select(Country).where(Country.market == market))
        }
        self._cities = {
            c.external_id: c for c in session.scalars(select(City).where(City.market == market))
        }
        self._attractions = {
            a.external_id: a
            for a in session.scalars(select(Attraction).where(Attraction.market == market))
        }
        self._products = {
            p.external_id: p
            for p in session.scalars(select(Product).where(Product.market == market))
        }
        self._russia_ids = {
            cid
            for cid, country in self._countries.items()
            if is_russia_country(code=country.code, name=country.name)
        }

    def _is_russia(self, country_id: str | None, country_name: str | None = None) -> bool:
        if country_id and country_id in self._russia_ids:
            return True
        if country_id:
            country = self._countries.get(country_id)
            if country and is_russia_country(code=country.code, name=country.name):
                return True
        return is_russia_country(name=country_name)

    def resolve(
        self,
        *,
        entity_type: str,
        entity_external_id: str,
        product_ids: list[str] | None = None,
    ) -> TopicGeo:
        country_id: str | None = None
        city_id: str | None = None
        attraction_id: str | None = None
        country_name: str | None = None

        if entity_type == EntityType.COUNTRY:
            country_id = entity_external_id
        elif entity_type == EntityType.CITY:
            city_id = entity_external_id
            city = self._cities.get(city_id)
            if city is not None:
                country_id = city.country_external_id
                country_name = city.country_name
        elif entity_type == EntityType.ATTRACTION:
            attraction_id = entity_external_id
            attraction = self._attractions.get(attraction_id)
            if attraction is not None:
                city_id = attraction.city_external_id
                city = self._cities.get(city_id or "")
                if city is not None:
                    country_id = city.country_external_id
                    country_name = city.country_name
        elif entity_type in {EntityType.CATEGORY, EntityType.COLLECTION}:
            city_id = _city_id_from_compound(entity_external_id)
            city = self._cities.get(city_id or "")
            if city is not None:
                country_id = city.country_external_id
                country_name = city.country_name
        elif entity_type == EntityType.PRODUCT:
            product = self._products.get(entity_external_id)
            if product is not None:
                city_id = product.city_external_id
                country_id = product.country_external_id

        if (country_id is None or city_id is None) and product_ids:
            for pid in product_ids:
                product = self._products.get(pid)
                if product is None:
                    continue
                city_id = city_id or product.city_external_id
                country_id = country_id or product.country_external_id
                if country_id and city_id:
                    break

        if country_name is None and city_id:
            city = self._cities.get(city_id)
            if city is not None:
                country_name = city.country_name
                country_id = country_id or city.country_external_id

        return TopicGeo(
            country_id=country_id,
            city_id=city_id,
            attraction_id=attraction_id,
            is_russia=self._is_russia(country_id, country_name),
        )

    def resolve_topic(self, topic: TopicCandidate) -> TopicGeo:
        return self.resolve(
            entity_type=topic.entity_type,
            entity_external_id=topic.entity_external_id,
            product_ids=list(topic.relevant_product_ids or []),
        )


__all__ = [
    "RUSSIA_COUNTRY_CODES",
    "RUSSIA_COUNTRY_NAMES",
    "GeoResolver",
    "TopicGeo",
    "is_russia_country",
]
