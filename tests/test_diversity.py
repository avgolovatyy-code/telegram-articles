"""Destination diversity and RU domestic preference."""

from __future__ import annotations

from app.db.enums import EntityType, TopicStatus
from app.db.models import City, Country, TopicCandidate
from app.topics.diversity import select_diverse_topics
from app.topics.geo import GeoResolver, is_russia_country


def _topic(
    session,
    *,
    market: str,
    entity_type: str,
    entity_id: str,
    name: str,
    score: float,
    index: int,
) -> TopicCandidate:
    topic = TopicCandidate(
        market=market,
        topic_key=f"{market}:{entity_type}:{entity_id}:things_to_do:{index}",
        topic_slug=f"{name.lower()}-{index}",
        entity_type=entity_type,
        entity_external_id=entity_id,
        entity_name=name,
        intent="things_to_do",
        primary_query=f"things to do in {name}",
        canonical_query=f"things to do in {name}",
        status=TopicStatus.CANDIDATE,
        topic_score=score,
        boost=0.0,
        inventory_depth=5,
    )
    session.add(topic)
    session.flush()
    return topic


def test_is_russia_country_helpers():
    assert is_russia_country(code="RU")
    assert is_russia_country(name="Россия")
    assert not is_russia_country(code="ES", name="Испания")


def test_select_diverse_topics_caps_same_city(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "max_same_city_per_day", 1)
    monkeypatch.setattr(settings, "ru_prefer_domestic", False)
    session.add(
        City(
            market="en",
            external_id="1",
            slug="paris",
            name="Paris",
            country_external_id="fr",
            country_name="France",
            product_count=10,
        )
    )
    session.add(
        City(
            market="en",
            external_id="2",
            slug="rome",
            name="Rome",
            country_external_id="it",
            country_name="Italy",
            product_count=8,
        )
    )
    session.flush()
    _topic(
        session,
        market="en",
        entity_type="city",
        entity_id="1",
        name="Paris",
        score=0.99,
        index=1,
    )
    _topic(
        session,
        market="en",
        entity_type="city",
        entity_id="1",
        name="Paris",
        score=0.98,
        index=2,
    )
    _topic(
        session,
        market="en",
        entity_type="city",
        entity_id="2",
        name="Rome",
        score=0.90,
        index=3,
    )

    selected = select_diverse_topics(session, "en", 3, settings=settings)
    cities = [t.entity_external_id for t in selected]
    assert cities.count("1") == 1
    assert "2" in cities


def test_ru_selection_prefers_domestic_when_available(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "ru_prefer_domestic", True)
    monkeypatch.setattr(settings, "ru_domestic_share", 0.7)
    monkeypatch.setattr(settings, "max_same_city_per_day", 1)
    session.add(
        Country(
            market="ru",
            external_id="2017370",
            code="RU",
            name="Россия",
            slug="russia",
        )
    )
    session.add(Country(market="ru", external_id="es", code="ES", name="Испания", slug="spain"))
    session.add(
        City(
            market="ru",
            external_id="msk",
            slug="moscow",
            name="Москва",
            country_external_id="2017370",
            country_name="Россия",
            product_count=20,
        )
    )
    session.add(
        City(
            market="ru",
            external_id="bcn",
            slug="barcelona",
            name="Барселона",
            country_external_id="es",
            country_name="Испания",
            product_count=40,
        )
    )
    session.flush()
    # Higher score for Barcelona, but Moscow should still be preferred under quota.
    _topic(
        session,
        market="ru",
        entity_type="city",
        entity_id="bcn",
        name="Барселона",
        score=0.99,
        index=1,
    )
    _topic(
        session,
        market="ru",
        entity_type="city",
        entity_id="msk",
        name="Москва",
        score=0.80,
        index=2,
    )
    _topic(
        session,
        market="ru",
        entity_type="city",
        entity_id="bcn",
        name="Барселона again",
        score=0.95,
        index=3,
    )

    selected = select_diverse_topics(session, "ru", 2, settings=settings)
    names = [t.entity_name for t in selected]
    assert "Москва" in names
    assert names.count("Барселона") + names.count("Барселона again") == 1


def test_geo_resolver_reads_category_city(session, settings):
    session.add(
        City(
            market="ru",
            external_id="524901",
            slug="moscow",
            name="Москва",
            country_external_id="2017370",
            country_name="Россия",
        )
    )
    session.add(
        Country(
            market="ru",
            external_id="2017370",
            code="RU",
            name="Россия",
            slug="russia",
        )
    )
    session.flush()
    resolver = GeoResolver(session, "ru")
    geo = resolver.resolve(entity_type=EntityType.CATEGORY, entity_external_id="3@524901")
    assert geo.city_id == "524901"
    assert geo.is_russia is True
