"""Product selection, the writer context and the deterministic quality gate."""

from __future__ import annotations

import pytest

from app.db.enums import ClaimStatus
from app.db.models import Product, ProductAttraction, TopicCandidate
from app.generation.context import ContextBuilder
from app.generation.product_selection import (
    MAX_PRODUCTS_PER_ARTICLE,
    RANK_WEIGHTS,
    ProductSelector,
    product_facts,
    product_summary,
)
from app.generation.quality import BANNED_PHRASES, QualityGate, normalize_hashtags
from app.generation.schemas import (
    ArticleBlock,
    ArticleDocument,
    ArticleSection,
    QualityReview,
)


def add_product(session, **kwargs) -> Product:
    defaults = {
        "market": "en",
        "slug": "tour",
        "title": "Tour",
        "available": True,
        "published": True,
        "city_external_id": "2988507",
    }
    product = Product(**{**defaults, **kwargs})
    session.add(product)
    session.flush()
    return product


def add_topic(session, **kwargs) -> TopicCandidate:
    defaults = {
        "market": "en",
        "topic_key": "en:city:2988507:things_to_do",
        "topic_slug": "en-paris-things-to-do",
        "entity_type": "city",
        "entity_external_id": "2988507",
        "entity_name": "Paris",
        "intent": "things_to_do",
        "primary_query": "things to do in Paris",
        "canonical_query": "do paris things",
        "secondary_queries": ["best things to do in Paris"],
        "inventory_depth": 5,
    }
    topic = TopicCandidate(**{**defaults, **kwargs})
    session.add(topic)
    session.flush()
    return topic


def test_rank_weights_match_the_specification():
    assert RANK_WEIGHTS == {
        "relevance": 0.45,
        "popularity": 0.20,
        "quality": 0.15,
        "availability": 0.10,
        "commercial_fit": 0.10,
    }


def test_relevance_beats_price(session, settings):
    topic = add_topic(session)
    relevant = add_product(
        session,
        external_id="1",
        title="Paris: Louvre Skip-the-Line Ticket & Audio Tour",
        short_description="A self-guided audio tour of the Louvre in Paris.",
        price=20.0,
        rating=4.7,
        reviews_count=300,
        popularity_rank=1,
    )
    expensive_irrelevant = add_product(
        session,
        external_id="2",
        title="Reykjavik: Northern Lights Boat Trip",
        short_description="A boat trip in Iceland.",
        city_external_id="9999",
        price=250.0,
        rating=4.9,
        reviews_count=900,
        popularity_rank=2,
    )
    ranked = ProductSelector(settings).rank(topic, [relevant, expensive_irrelevant])
    assert ranked
    assert ranked[0].product.external_id == relevant.external_id


def test_unavailable_products_are_never_selected(session, settings):
    topic = add_topic(session)
    add_product(session, external_id="3", title="Paris tour", available=False)
    assert ProductSelector(settings).rank(topic, session.query(Product).all()) == []


def test_selection_is_capped(session, settings):
    topic = add_topic(session)
    products = [
        add_product(
            session,
            external_id=str(100 + i),
            title=f"Paris audio tour {i}",
            short_description="things to do in Paris",
            popularity_rank=i,
        )
        for i in range(12)
    ]
    topic.relevant_product_ids = [p.external_id for p in products]
    catalog = {p.external_id: p for p in products}
    selected = ProductSelector(settings).select(topic, catalog)
    assert 0 < len(selected) <= MAX_PRODUCTS_PER_ARTICLE


def test_selected_products_use_compact_placement(session, settings):
    topic = add_topic(session)
    products = [
        add_product(session, external_id=str(200 + i), title=f"Paris tour {i}", popularity_rank=i)
        for i in range(3)
    ]
    topic.relevant_product_ids = [p.external_id for p in products]
    selected = ProductSelector(settings).select(topic, {p.external_id: p for p in products})
    assert selected
    assert all(item.placement == "compact" for item in selected)


def test_attraction_topics_prefer_products_linked_to_that_attraction(session, settings):
    topic = add_topic(
        session,
        topic_key="en:attraction:2285:what_to_see",
        entity_type="attraction",
        entity_external_id="2285",
        entity_name="The Louvre",
        primary_query="what to see at The Louvre",
    )
    linked = add_product(session, external_id="10", title="Museum entry", popularity_rank=5)
    linked.attractions.append(
        ProductAttraction(attraction_external_id="2285", name="The Louvre", slug="louvre")
    )
    other = add_product(session, external_id="11", title="Museum entry", popularity_rank=1)
    session.flush()
    ranked = ProductSelector(settings).rank(topic, [linked, other])
    assert ranked[0].product.external_id == "10"


def test_product_facts_only_report_api_fields(session):
    product = add_product(
        session,
        external_id="20",
        title="Tour",
        duration_min=90,
        duration_max=90,
        price=12.0,
        currency_code="EUR",
        rating=4.5,
        reviews_count=10,
        inclusions=["Entrance ticket"],
    )
    facts = product_facts(product)
    assert any("90 min" in fact for fact in facts)
    assert any("12.0 EUR" in fact for fact in facts)
    assert all("WeGoTrip API" in fact for fact in facts)


def test_product_summary_is_compact(session):
    product = add_product(
        session, external_id="21", title="Tour", description="x" * 5000, price=10.0
    )
    summary = product_summary(product)
    assert len(summary["short_description"]) <= 600
    assert set(summary) >= {"id", "title", "price", "available"}


# ------------------------------------------------------------------ context
def test_context_contains_everything_the_writer_needs(synced_session, settings):
    topic = add_topic(synced_session)
    products = synced_session.query(Product).filter_by(market="en").limit(3).all()
    topic.relevant_product_ids = [p.external_id for p in products]
    ranked = ProductSelector(settings).rank(topic, products)
    context = ContextBuilder(synced_session, settings).build(topic, ranked)
    payload = context.as_payload(settings)

    assert payload["market"] == "en"
    assert payload["primary_query"] == "things to do in Paris"
    assert payload["entity"]["name"] == "Paris"
    assert payload["catalog_facts"]
    assert payload["catalog_attractions"], "city topics must expose catalogue attractions"
    assert payload["forbidden_claims"]
    assert payload["article_constraints"]["max_chars"] == settings.article_target_max_chars
    assert payload["article_constraints"]["min_named_catalog_attractions"] >= 2
    assert "brand_style" in payload
    for product in payload["products"]:
        assert "url" not in product  # the writer must never see a link


def test_only_api_media_is_offered(synced_session, settings):
    topic = add_topic(synced_session)
    products = synced_session.query(Product).filter_by(market="en").limit(3).all()
    topic.relevant_product_ids = [p.external_id for p in products]
    ranked = ProductSelector(settings).rank(topic, products)
    context = ContextBuilder(synced_session, settings).build(topic, ranked)
    assert context.media
    assert all(item.url.startswith("http") for item in context.media)
    assert all(
        item.source_entity_type in {"attraction", "city", "product"} for item in context.media
    )


# ------------------------------------------------------------- quality gate
def base_document(text: str = "Paris is a good place to start walking.") -> ArticleDocument:
    long_text = (text + " ") * 30
    return ArticleDocument(
        title="Things to Do in Paris: A Practical Guide",
        intro="Things to do in Paris, starting with the Pantheon and a short walk downhill.",
        sections=[
            ArticleSection(
                heading=f"Things to do in Paris, part {index}",
                blocks=[ArticleBlock(type="paragraph", text=f"{index}. {long_text}")],
            )
            for index in range(4)
        ],
    )


@pytest.fixture()
def context(synced_session, settings):
    topic = add_topic(synced_session)
    products = synced_session.query(Product).filter_by(market="en").limit(2).all()
    topic.relevant_product_ids = [p.external_id for p in products]
    ranked = ProductSelector(settings).rank(topic, products)
    return ContextBuilder(synced_session, settings).build(topic, ranked)


def test_gate_rejects_a_too_short_article(context, settings):
    document = ArticleDocument(title="T", intro="Short.", sections=[])
    result = QualityGate(settings).technical(document, context, [])
    assert not result.passed
    assert any("too short" in error for error in result.errors)


def test_gate_rejects_banned_boilerplate(context, settings):
    document = base_document(BANNED_PHRASES["en"][0] + " the city of light.")
    result = QualityGate(settings).content(document, context)
    assert not result.passed
    assert any("boilerplate" in error for error in result.errors)


def test_gate_rejects_watery_article_without_named_attractions(context, settings):
    if len(context.catalog_attractions) < 3:
        pytest.skip("fixture catalogue has too few attractions")
    watery = (
        "Choose one focus for the day and leave free time around it. "
        "Do not turn the city into a checklist of obligations. "
        "A calm rhythm beats collecting pins on a map."
    )
    document = base_document(watery)
    result = QualityGate(settings).content(document, context)
    assert not result.passed
    assert any("too abstract" in error for error in result.errors)


def test_gate_accepts_russian_aliases_for_latin_attraction_names():
    from app.generation.place_names import attraction_mentioned
    from app.topics.dedup import normalize_text

    body = normalize_text(
        "Начните с Саграды Фамилии, затем Парк Гуэль и музей Пикассо."
    )
    assert attraction_mentioned("Basílica de la Sagrada Família", body)
    assert attraction_mentioned("Park Guell", body)
    assert attraction_mentioned("Museu Picasso de Barcelona", body)
    assert not attraction_mentioned(
        "Музей современного искусства",
        normalize_text("Билет в Музей Бенкси без очереди."),
    )


def test_gate_rejects_an_unknown_product(context, settings):
    from app.generation.schemas import ProductPlacement

    document = base_document()
    document.product_placements = [ProductPlacement(product_id="does-not-exist")]
    result = QualityGate(settings).technical(document, context, [])
    assert any("not in the selected set" in error for error in result.errors)


def test_gate_rejects_a_link_without_the_affiliate_marker(context, settings):
    result = QualityGate(settings).technical(
        base_document(), context, ["https://wegotrip.com/paris-d2988507/"]
    )
    assert any("affiliate marker" in error for error in result.errors)


def test_gate_accepts_a_marked_link(context, settings):
    result = QualityGate(settings).technical(
        base_document(), context, ["https://wegotrip.com/paris-d2988507/?coupon=435"]
    )
    assert result.passed


def test_gate_blocks_unverified_critical_claims(settings):
    result = QualityGate(settings).factual(
        [("The museum is closed on Tuesdays.", ClaimStatus.UNVERIFIED, True)]
    )
    assert not result.passed


def test_gate_allows_verified_claims(settings):
    result = QualityGate(settings).factual(
        [("The museum is closed on Tuesdays.", ClaimStatus.VERIFIED, True)]
    )
    assert result.passed


def test_gate_enforces_the_factuality_threshold(settings):
    review = QualityReview(
        usefulness=0.95,
        factuality=0.90,
        readability=0.95,
        search_intent_match=0.95,
        natural_language=0.95,
        product_relevance=0.95,
        spam_risk=0.01,
    )
    result = QualityGate(settings).review_thresholds(review)
    assert not result.passed
    assert any("factuality" in error for error in result.errors)


def test_gate_accepts_a_good_review(settings):
    review = QualityReview(
        usefulness=0.95,
        factuality=0.99,
        readability=0.95,
        search_intent_match=0.95,
        natural_language=0.95,
        product_relevance=0.93,
        spam_risk=0.01,
    )
    assert QualityGate(settings).review_thresholds(review).passed


def test_gate_flags_keyword_stuffing(context, settings):
    document = base_document("Paris Paris Paris Paris Paris Paris.")
    result = QualityGate(settings).search(document, context)
    assert any("stuffing" in error for error in result.errors)


def test_gate_requires_the_entity_on_the_first_screen(context, settings):
    document = base_document()
    document.title = "A Practical Guide"
    document.intro = "Somewhere nice, in general terms, with no names at all."
    result = QualityGate(settings).search(document, context)
    assert not result.passed


def test_hashtags_are_normalised_and_capped(settings):
    tags = normalize_hashtags(
        ["Paris", "#Louvre", "#Louvre", "not a tag!", "#a", "#b", "#c"], settings
    )
    assert tags[0] == "#Paris"
    assert len(tags) <= settings.max_hashtags
    assert len(set(tags)) == len(tags)
