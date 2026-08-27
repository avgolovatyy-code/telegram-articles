"""Intent clusters, RU morphology, canonicalization, deduplication and scoring."""

from __future__ import annotations

from app.config import MARKETS
from app.db.enums import EntityType, TopicStatus
from app.db.models import TopicCandidate
from app.topics.clusters import load_seed_clusters
from app.topics.dedup import (
    DeduplicationService,
    canonicalize_query,
    similarity,
    topic_key,
)
from app.topics.demand import HEURISTIC_MAX_CONFIDENCE, HeuristicDemandProvider
from app.topics.discovery import TopicDiscoveryService
from app.topics.morphology import inflect_ru, render_pattern
from app.topics.scoring import DEFAULT_WEIGHTS, ScoreInputs, effective_weights, score_topic

ALL_ENTITY_TYPES = {e.value for e in EntityType}


def test_every_market_has_a_cluster_for_every_entity_type():
    for market in MARKETS:
        clusters = load_seed_clusters(market)
        assert clusters, f"no clusters for {market}"
        covered = {cluster.entity_type for cluster in clusters}
        assert covered == ALL_ENTITY_TYPES, f"{market} misses {ALL_ENTITY_TYPES - covered}"


def test_en_and_ru_clusters_are_independent():
    en = {c.primary_pattern for c in load_seed_clusters("en")}
    ru = {c.primary_pattern for c in load_seed_clusters("ru")}
    assert not (en & ru), "RU patterns must not be copies of EN patterns"


def test_russian_declension():
    assert inflect_ru("Париж", "loct") == "Париже"
    assert inflect_ru("Москва", "datv") == "Москве"
    assert inflect_ru("Санкт-Петербург", "loct") == "Санкт-Петербурге"
    assert inflect_ru("Эрмитаж", "gent") == "Эрмитажа"


def test_ru_patterns_render_grammatically():
    rendered = render_pattern("что посмотреть в {entity:loct}", {"entity": "Париж"}, market="ru")
    assert rendered == "что посмотреть в Париже"


def test_unknown_word_falls_back_to_nominative():
    assert render_pattern("аудиогид по {entity:datv}", {"entity": "Zzyzx"}, market="ru").endswith(
        "Zzyzx"
    )


def test_en_patterns_are_untouched():
    assert render_pattern("things to do in {entity}", {"entity": "Paris"}, market="en") == (
        "things to do in Paris"
    )


# ------------------------------------------------------------------- dedup
def test_canonicalization_collapses_modifier_variants():
    variants = [
        "things to do in Paris",
        "Best things to do in Paris",
        "What are the best things to do in Paris",
        "Top things to do in Paris",
    ]
    canonical = {canonicalize_query(v, "en") for v in variants}
    assert len(canonical) == 1


def test_ru_canonicalization():
    assert canonicalize_query("что посмотреть в Париже", "ru") == canonicalize_query(
        "Что обязательно посмотреть в Париже", "ru"
    )


def test_similarity_is_high_for_paraphrases_and_low_for_different_topics():
    assert similarity("things to do in Paris", "best things to do in Paris") > 0.8
    assert similarity("things to do in Paris", "walking tours in Rome") < 0.5


def test_topic_key_is_stable():
    assert topic_key("en", "city", "3", "things_to_do") == "en:city:3:things_to_do"


def test_dedup_blocks_a_second_topic_for_the_same_entity_and_intent(session, settings):
    session.add(
        TopicCandidate(
            market="en",
            topic_key=topic_key("en", "city", "3", "things_to_do"),
            topic_slug="en-paris-things-to-do",
            entity_type="city",
            entity_external_id="3",
            entity_name="Paris",
            intent="things_to_do",
            primary_query="things to do in Paris",
            canonical_query=canonicalize_query("things to do in Paris", "en"),
            status=TopicStatus.QUEUED,
        )
    )
    session.flush()

    verdict = DeduplicationService(session, settings).check_topic(
        "en",
        entity_type="city",
        entity_external_id="3",
        entity_name="Paris",
        intent="things_to_do",
        primary_query="best things to do in Paris",
    )
    assert verdict.is_duplicate


def test_dedup_allows_a_different_intent_for_the_same_entity(session, settings):
    session.add(
        TopicCandidate(
            market="en",
            topic_key=topic_key("en", "city", "3", "things_to_do"),
            topic_slug="en-paris-things-to-do",
            entity_type="city",
            entity_external_id="3",
            entity_name="Paris",
            intent="things_to_do",
            primary_query="things to do in Paris",
            canonical_query=canonicalize_query("things to do in Paris", "en"),
            status=TopicStatus.QUEUED,
        )
    )
    session.flush()

    verdict = DeduplicationService(session, settings).check_topic(
        "en",
        entity_type="city",
        entity_external_id="3",
        entity_name="Paris",
        intent="museums",
        primary_query="best museums in Paris",
    )
    assert not verdict.is_duplicate


# ------------------------------------------------------------------ scoring
def test_missing_demand_signal_redistributes_its_weight():
    weights = effective_weights(DEFAULT_WEIGHTS, has_demand_signal=False)
    assert weights["search_demand"] == 0.0
    assert weights["inventory_depth"] > DEFAULT_WEIGHTS["inventory_depth"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_thin_content_is_penalised():
    base = ScoreInputs(
        demand_score=0.8,
        demand_confidence=0.5,
        inventory_depth=10,
        min_inventory=5,
        entity_popularity=0.8,
        product_quality=0.8,
        commercial_relevance=0.8,
        freshness=0.5,
        content_diversity=0.8,
    )
    thin = ScoreInputs(
        demand_score=0.8,
        demand_confidence=0.5,
        inventory_depth=1,
        min_inventory=5,
        entity_popularity=0.8,
        product_quality=0.8,
        commercial_relevance=0.8,
        freshness=0.5,
        content_diversity=0.8,
    )
    assert score_topic(base).score > score_topic(thin).score
    assert "thin_content" in score_topic(thin).penalties


def test_heuristic_demand_never_claims_high_confidence():
    provider = HeuristicDemandProvider()
    signal = provider.get_demand(
        "things to do in Paris",
        "en",
        entity_popularity=1.0,
        inventory_depth=50,
        intent="things_to_do",
    )
    assert signal.source == "heuristic"
    assert signal.confidence <= HEURISTIC_MAX_CONFIDENCE


# ---------------------------------------------------------------- discovery
def test_discovery_covers_multiple_catalogue_levels(synced_session, settings):
    service = TopicDiscoveryService(synced_session, settings=settings)
    stats = service.discover("en", limit=120)
    assert stats.created > 0
    covered = set(stats.by_entity_type)
    assert {"city", "attraction"} <= covered
    assert len(covered) >= 3, f"only covered {covered}"


def test_discovery_is_idempotent(synced_session, settings):
    service = TopicDiscoveryService(synced_session, settings=settings)
    first = service.discover("ru", limit=60)
    before = synced_session.query(TopicCandidate).filter_by(market="ru").count()
    service.discover("ru", limit=60)
    after = synced_session.query(TopicCandidate).filter_by(market="ru").count()
    assert first.created > 0
    assert after == before


def test_ru_topics_use_russian_queries(synced_session, settings):
    TopicDiscoveryService(synced_session, settings=settings).discover("ru", limit=40)
    topics = synced_session.query(TopicCandidate).filter_by(market="ru").all()
    assert topics
    assert all(any("\u0400" <= ch <= "\u04ff" for ch in t.primary_query) for t in topics)
