"""Rich message building, product cards, media validation and channel routing."""

from __future__ import annotations

import pytest

from app.db.models import Article, Product
from app.generation.schemas import (
    ArticleBlock,
    ArticleDocument,
    ArticleSection,
    FAQItem,
    MediaPlacement,
    ProductPlacement,
)
from app.links.affiliate import AffiliateLinkBuilder, LinkContext
from app.media_assets import MediaCandidate
from app.telegram import blocks as tb
from app.telegram.api import DryRunTelegramClient
from app.telegram.media import MediaValidator
from app.telegram.product_cards import TelegramProductCardRenderer
from app.telegram.publisher import TelegramPublisher, idempotency_key
from app.telegram.renderer import RichMessageRenderer


@pytest.fixture()
def product(session) -> Product:
    row = Product(
        market="en",
        external_id="4900",
        slug="paris-pantheon",
        title="Paris: Pantheon Ticket & National Pride Audio Tour",
        cover="https://cdn.example/cover.jpg",
        preview="https://cdn.example/preview.jpg",
        price=18.52,
        currency_code="EUR",
        currency_symbol="€",
        rating=4.6,
        reviews_count=192,
        duration_min=60,
        duration_max=90,
        available=True,
        published=True,
        types={"audioguide": True},
        highlights=["Skip the queue with a timed ticket"],
        city_external_id="2988507",
        canonical_url="https://wegotrip.com/paris-d2988507/paris-pantheon-p4900/",
    )
    session.add(row)
    session.flush()
    return row


@pytest.fixture()
def bare_product(session) -> Product:
    """A product where the API returned no price, rating or duration."""
    row = Product(
        market="en",
        external_id="7000",
        slug="mystery-walk",
        title="Mystery Walk",
        available=True,
        published=True,
    )
    session.add(row)
    session.flush()
    return row


def sample_document() -> ArticleDocument:
    return ArticleDocument(
        title="Things to Do in Paris: A Practical Guide",
        intro="Short answer first: start at the Pantheon and walk downhill.",
        sections=[
            ArticleSection(
                heading="Start here",
                blocks=[
                    ArticleBlock(type="paragraph", text="Go early, the queue builds after ten."),
                    ArticleBlock(type="list", items=["Bring headphones", "Charge your phone"]),
                    ArticleBlock(type="quote", text="A quiet courtyard beats a crowded nave."),
                    ArticleBlock(type="table", rows=[["Stop", "Time"], ["Pantheon", "60 min"]]),
                ],
            ),
            ArticleSection(
                heading="A half-day route",
                blocks=[ArticleBlock(type="paragraph", text="Walk down to the river.")],
            ),
        ],
        product_placements=[
            ProductPlacement(product_id="4900", placement="hero", after_section=0, pitch="Why")
        ],
        media_placements=[MediaPlacement(media_id="m1", after_section=1)],
        faq=[FAQItem(question="How long?", answer="About an hour.")],
        hashtags=["#Paris", "#Pantheon"],
    )


# ------------------------------------------------------------------- blocks
def test_block_builders_produce_official_shapes():
    assert tb.paragraph("x") == {"type": "paragraph", "text": "x"}
    assert tb.heading("x", 1)["size"] == 1
    assert tb.divider() == {"type": "divider"}
    assert tb.bullet_list(["a"])["items"][0]["blocks"][0]["type"] == "paragraph"
    assert tb.ordered_list(["a"])["items"][0]["value"] == 1
    assert tb.photo("https://x/y.jpg")["photo"]["media"] == "https://x/y.jpg"
    assert tb.audio("https://x/y.mp3", title="t")["audio"]["title"] == "t"
    assert tb.voice_note("https://x/y.ogg")["type"] == "voice_note"
    assert tb.buttons([tb.url_button("Go", "https://x")])["buttons"][0]["url"] == "https://x"


def test_validation_accepts_a_normal_message():
    message = tb.rich_message([tb.heading("T", 1), tb.paragraph("Body")])
    assert tb.validate_rich_message(message) == []


def test_validation_rejects_an_empty_message():
    assert tb.validate_rich_message({"blocks": []})


def test_validation_enforces_the_character_limit():
    message = tb.rich_message([tb.paragraph("x" * (tb.CHAR_LIMIT + 1))])
    assert any("characters" in error for error in tb.validate_rich_message(message))


def test_validation_enforces_the_block_limit():
    message = tb.rich_message([tb.paragraph("x")] * (tb.BLOCK_LIMIT + 1))
    assert any("blocks" in error for error in tb.validate_rich_message(message))


def test_table_builder_truncates_to_the_column_limit():
    built = tb.table([["c"] * (tb.TABLE_COLUMN_LIMIT + 5)])
    assert len(built["cells"][0]) == tb.TABLE_COLUMN_LIMIT


def test_validation_enforces_the_table_column_limit():
    oversized = {
        "type": "table",
        "cells": [[{"text": "c"}] * (tb.TABLE_COLUMN_LIMIT + 1)],
    }
    assert any("columns" in error for error in tb.validate_rich_message({"blocks": [oversized]}))


# -------------------------------------------------------------- product cards
def test_hero_card_shows_only_api_backed_facts(product, settings):
    renderer = TelegramProductCardRenderer(settings=settings)
    card = renderer.hero(product, "en", LinkContext(market="en", article_id="a1", topic_slug="t"))
    text = str(card.blocks)
    assert "⭐ 4.6" in text
    assert "192 reviews" in text
    assert "60–90 min" in text
    assert "from 18.52 €" in text
    assert card.url.startswith("https://wegotrip.com/paris-d2988507/")
    assert "coupon=435" in card.url
    photos = [b for b in card.blocks if b.get("type") == "photo"]
    assert len(photos) == 1
    assert "caption" not in photos[0].get("photo", {})


def test_hero_skips_photo_when_url_already_used(product, settings):
    renderer = TelegramProductCardRenderer(settings=settings)
    card = renderer.hero(
        product,
        "en",
        LinkContext(market="en", article_id="a1", topic_slug="t"),
        used_image_urls={product.cover},
    )
    assert not any(b.get("type") == "photo" for b in card.blocks)
    assert "🎧" in str(card.blocks)


def test_renderer_does_not_duplicate_product_cover_photo(product, settings):
    """Same product cover must not appear as media_placement and again in the hero card."""
    media = {
        "prod-cover": MediaCandidate(
            id="prod-cover",
            url=product.cover,
            kind="photo",
            source_entity_type="product",
            role="gallery",
            caption=product.title,
            product_external_id=product.external_id,
        )
    }
    document = sample_document()
    document.media_placements = [
        MediaPlacement(media_id="prod-cover", after_section=0, caption="Маршрут по Лувру")
    ]
    document.product_placements = [
        ProductPlacement(product_id="4900", placement="hero", after_section=0, pitch="Why")
    ]
    rendered = RichMessageRenderer(settings=settings).render(
        document,
        market="en",
        products={"4900": product},
        media=media,
        link_context=LinkContext(market="en", article_id="a1", topic_slug="t"),
        entity_name="Paris",
    )
    photos = [b for b in rendered.message["blocks"] if b.get("type") == "photo"]
    urls = [b["photo"]["media"] for b in photos]
    assert urls.count(product.cover) == 1
    assert sum(1 for u in urls if u == product.cover) == 1
    assert "🎧" in str(rendered.message)


def test_card_omits_facts_the_api_did_not_return(bare_product, settings):
    renderer = TelegramProductCardRenderer(settings=settings)
    card = renderer.compact(
        bare_product, "en", LinkContext(market="en", article_id="a1", topic_slug="t")
    )
    text = str(card.blocks)
    assert "⭐" not in text
    assert "from" not in text


def test_ru_card_uses_the_ru_domain_and_labels(product, settings):
    renderer = TelegramProductCardRenderer(settings=settings)
    card = renderer.hero(product, "ru", LinkContext(market="ru", article_id="a1", topic_slug="t"))
    assert "wegotrip.ru" in card.url
    assert "utm_campaign=wegotrip_ru" in card.url
    assert "Билет и аудиогид" in str(card.blocks)


def test_collection_block_lists_products(product, bare_product, settings):
    renderer = TelegramProductCardRenderer(settings=settings)
    blocks, cards = renderer.collection(
        [product, bare_product],
        "en",
        LinkContext(market="en", article_id="a1", topic_slug="t"),
        entity_name="Paris",
    )
    assert len(cards) == 2
    assert "Explore Paris with WeGoTrip" in str(blocks)


# ------------------------------------------------------------------ renderer
def test_renderer_builds_a_valid_rich_message(product, settings):
    media = {
        "m1": MediaCandidate(
            id="m1",
            url="https://cdn.example/city.jpg",
            kind="photo",
            source_entity_type="city",
            role="cover",
        )
    }
    rendered = RichMessageRenderer(settings=settings).render(
        sample_document(),
        market="en",
        products={"4900": product},
        media=media,
        link_context=LinkContext(market="en", article_id="a1", topic_slug="en-paris-things-to-do"),
        entity_name="Paris",
    )
    assert tb.validate_rich_message(rendered.message) == []
    types = [block["type"] for block in rendered.message["blocks"]]
    assert types[0] == "photo"  # cover first
    assert "heading" in types and "list" in types and "table" in types
    assert "details" in types  # FAQ
    assert "footer" in types  # hashtags
    assert rendered.product_cards


def test_renderer_never_emits_an_unmarked_store_url(product, settings):
    rendered = RichMessageRenderer(settings=settings).render(
        sample_document(),
        market="en",
        products={"4900": product},
        media={},
        link_context=LinkContext(market="en", article_id="a1", topic_slug="t"),
        entity_name="Paris",
    )
    builder = AffiliateLinkBuilder(settings)
    store_urls = [url for url in rendered.urls if builder.is_store_url(url)]
    assert store_urls
    assert all(builder.has_affiliate_marker(url) for url in store_urls)


def test_renderer_honours_the_hashtag_limit(product, settings):
    document = sample_document()
    document.hashtags = ["#a", "#b", "#c", "#d", "#e", "#f"]
    rendered = RichMessageRenderer(settings=settings).render(
        document,
        market="en",
        products={"4900": product},
        media={},
        link_context=LinkContext(market="en", article_id="a1", topic_slug="t"),
        entity_name="Paris",
    )
    assert len(rendered.hashtags) <= settings.max_hashtags


def test_renderer_uses_the_tracking_resolver(product, settings):
    rendered = RichMessageRenderer(settings=settings).render(
        sample_document(),
        market="en",
        products={"4900": product},
        media={},
        link_context=LinkContext(market="en", article_id="a1", topic_slug="t"),
        entity_name="Paris",
        url_resolver=lambda pid, placement: f"https://engine.example/r/{pid}-{placement}",
    )
    assert "https://engine.example/r/4900-hero" in rendered.urls


def test_audio_block_only_appears_when_a_url_exists(product, settings):
    from app.generation.schemas import AudioPlacement

    document = sample_document()
    document.audio_placements = [AudioPlacement(product_id="4900", after_section=0)]
    renderer = RichMessageRenderer(settings=settings)

    without = renderer.render(
        document,
        market="en",
        products={"4900": product},
        media={},
        link_context=LinkContext(market="en", article_id="a1", topic_slug="t"),
        entity_name="Paris",
    )
    assert not any(b["type"] == "audio" for b in without.message["blocks"])

    with_audio = renderer.render(
        document,
        market="en",
        products={"4900": product},
        media={},
        link_context=LinkContext(market="en", article_id="a1", topic_slug="t"),
        entity_name="Paris",
        audio_urls={"4900": "https://cdn.example/preview.mp3"},
    )
    assert any(b["type"] == "audio" for b in with_audio.message["blocks"])


# ------------------------------------------------------------ media validation
def test_media_validator_rejects_http_and_bad_extensions(settings):
    validator = MediaValidator(settings)
    assert not validator.check("http://cdn.example/a.jpg").ok
    assert not validator.check("https://cdn.example/a.txt").ok
    assert validator.check("https://cdn.example/a.jpg").ok


def test_media_validator_drops_duplicates(settings):
    validator = MediaValidator(settings)
    checks = validator.check_many(
        [("https://cdn.example/a.jpg", "photo"), ("https://cdn.example/a.jpg", "photo")]
    )
    assert checks[0].ok
    assert not checks[1].ok
    assert "duplicate" in (checks[1].error or "")


# --------------------------------------------------------------- publisher
def make_article(session, market: str = "en") -> Article:
    article = Article(
        public_id=f"pub-{market}",
        market=market,
        topic_slug="t",
        entity_type="city",
        entity_external_id="1",
        entity_name="Paris",
        intent="things_to_do",
        primary_query="things to do in Paris",
        status="approved",
        current_version=1,
    )
    session.add(article)
    session.flush()
    return article


def test_channel_routing_per_market(session, settings):
    publisher = TelegramPublisher(session, DryRunTelegramClient(settings), settings=settings)
    assert publisher.channel_for("en", "production") == settings.telegram_en_channel
    assert publisher.channel_for("ru", "production") == settings.telegram_ru_channel
    assert publisher.channel_for("en", "test") == settings.telegram_test_channel


def test_publishing_is_idempotent(session, settings):
    article = make_article(session)
    client = DryRunTelegramClient(settings)
    publisher = TelegramPublisher(session, client, settings=settings)
    message = tb.rich_message([tb.heading("T", 1), tb.paragraph("Body")])

    first = publisher.publish(article, message)
    second = publisher.publish(article, message)

    assert first.created is True
    assert second.created is False
    assert second.reused is True
    assert first.publication.message_id == second.publication.message_id
    assert len(client.sent) == 1


def test_a_new_version_gets_a_new_idempotency_key(session, settings):
    article = make_article(session, "ru")
    assert idempotency_key(article.id, 1, "production") != idempotency_key(
        article.id, 2, "production"
    )


def test_enqueue_is_idempotent(session, settings):
    article = make_article(session)
    publisher = TelegramPublisher(session, DryRunTelegramClient(settings), settings=settings)
    first = publisher.enqueue(article)
    second = publisher.enqueue(article)
    assert first.id == second.id


def test_claim_blocks_a_concurrent_worker(session, settings):
    article = make_article(session)
    publisher = TelegramPublisher(session, DryRunTelegramClient(settings), settings=settings)
    item = publisher.enqueue(article)
    assert publisher.claim(item, "worker-1") is True
    assert publisher.claim(item, "worker-2") is False
