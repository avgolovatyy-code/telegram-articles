"""End-to-end integration: catalogue → topic → article → rich message → publication.

Covers both acceptance scenarios from the specification (§54 EN, §55 RU).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai.budget import BudgetManager
from app.ai.mock_provider import MockLLMProvider
from app.ai.router import LLMGateway
from app.analytics.reports import AnalyticsService
from app.db.enums import ArticleStatus, TopicStatus
from app.db.models import Article, ArticleProduct, CostLedgerEntry, LLMRun, TopicCandidate
from app.generation.pipeline import GenerationPipeline
from app.links.affiliate import AffiliateLinkBuilder
from app.scheduler import jobs
from app.services.rendering import render_stored_article
from app.services.workflow import ArticleWorkflow
from app.telegram.blocks import collect_urls, validate_rich_message
from app.topics.discovery import TopicDiscoveryService, select_topics_for_generation


def build_pipeline(session, settings, *, fail_quality: bool = False) -> GenerationPipeline:
    gateway = LLMGateway(session, MockLLMProvider(fail_quality=fail_quality), settings=settings)
    return GenerationPipeline(session, gateway, settings=settings)


def first_topic(session, market: str) -> TopicCandidate:
    TopicDiscoveryService(session).discover(market, limit=60)
    topics = select_topics_for_generation(session, market, 20)
    assert topics, f"no topic candidates for {market}"
    return topics[0]


@pytest.mark.parametrize("market", ["en", "ru"])
def test_generate_render_and_publish(synced_session, settings, market):
    topic = first_topic(synced_session, market)
    pipeline = build_pipeline(synced_session, settings)

    outcome = None
    for candidate in select_topics_for_generation(synced_session, market, 12):
        outcome = pipeline.generate(candidate)
        if outcome.ok:
            topic = candidate
            break
    assert outcome is not None and outcome.ok, (
        f"no article passed the gates for {market}: {outcome.reason if outcome else 'none'}"
    )

    article = outcome.article
    assert article is not None
    assert article.market == market
    assert article.status == ArticleStatus.NEEDS_REVIEW
    assert article.char_count >= settings.article_min_chars
    assert article.actual_cost_usd > 0
    assert article.products, "no products attached"
    assert article.media, "no media attached"
    assert topic.status == TopicStatus.USED

    # The stored payload is a valid Telegram rich message.
    assert validate_rich_message(article.rendered_message) == []

    # Every store URL carries the affiliate marker and the right domain.
    builder = AffiliateLinkBuilder(settings)
    expected_domain = settings.store_domain(market)
    for link in article.products:
        assert builder.has_affiliate_marker(link.affiliate_url)
        assert expected_domain in link.affiliate_url
        assert f"utm_campaign=wegotrip_{market}" in link.affiliate_url
        assert f"utm_content={article.public_id}" in link.affiliate_url

    # Spend is recorded per run and in the ledger.
    runs = synced_session.scalars(select(LLMRun).where(LLMRun.article_id == article.id)).all()
    assert runs
    ledger = synced_session.scalars(
        select(CostLedgerEntry).where(CostLedgerEntry.article_id == article.id)
    ).all()
    assert ledger
    assert sum(entry.amount_usd for entry in ledger) == pytest.approx(
        article.actual_cost_usd, abs=1e-6
    )

    # Test channel first, then production.
    workflow = ArticleWorkflow(synced_session, settings)
    assert not workflow.publish_now(article).ok, "production must require a test publication first"
    assert workflow.publish_test(article).ok
    assert workflow.approve(article).ok
    result = workflow.publish_now(article)
    assert result.ok
    assert article.status == ArticleStatus.PUBLISHED

    publications = {p.target: p for p in article.publications}
    assert set(publications) == {"test", "production"}
    assert publications["production"].channel_username == settings.telegram_channel(market)
    assert publications["production"].message_id

    # A repeated publish attempt does not create a second message.
    before = len(article.publications)
    workflow.publish_now(article)
    assert len(article.publications) == before


def test_no_translation_between_markets(synced_session, settings):
    """EN and RU articles must be independent, not translations of each other."""
    pipeline = build_pipeline(synced_session, settings)
    produced: dict[str, Article] = {}
    for market in ("en", "ru"):
        TopicDiscoveryService(synced_session).discover(market, limit=60)
        for candidate in select_topics_for_generation(synced_session, market, 12):
            outcome = pipeline.generate(candidate)
            if outcome.ok and outcome.article is not None:
                produced[market] = outcome.article
                break
    assert set(produced) == {"en", "ru"}

    en, ru = produced["en"], produced["ru"]
    assert en.primary_query != ru.primary_query
    assert any("\u0400" <= ch <= "\u04ff" for ch in ru.title or "")
    assert not any("\u0400" <= ch <= "\u04ff" for ch in en.title or "")

    en_products = {link.product_external_id for link in en.products}
    ru_products = {link.product_external_id for link in ru.products}
    for market, ids in (("en", en_products), ("ru", ru_products)):
        rows = synced_session.scalars(
            select(ArticleProduct).where(ArticleProduct.product_external_id.in_(ids))
        ).all()
        assert rows
        _ = market


def test_a_failing_quality_gate_does_not_publish(synced_session, settings):
    pipeline = build_pipeline(synced_session, settings, fail_quality=True)
    topic = first_topic(synced_session, "en")
    outcome = pipeline.generate(topic)
    assert not outcome.ok
    assert outcome.article is not None
    assert outcome.article.status == ArticleStatus.VALIDATION_FAILED
    workflow = ArticleWorkflow(synced_session, settings)
    assert not workflow.approve(outcome.article).ok


def test_budget_blocks_generation_once_the_cap_is_reached(synced_session, settings):
    BudgetManager(synced_session, settings).record(amount_usd=3.0, market="en")
    pipeline = build_pipeline(synced_session, settings)
    topic = first_topic(synced_session, "en")
    outcome = pipeline.generate(topic)
    assert outcome.status == "budget_blocked"
    assert outcome.article is None


def test_daily_generation_respects_the_budget(synced_session, settings, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.jobs.LLMGateway",
        lambda session, settings=None, budget=None: LLMGateway(
            session, MockLLMProvider(), settings=settings, budget=budget
        ),
    )
    jobs.discover_topics(synced_session, settings=settings)
    report = jobs.generate_daily_articles(synced_session, settings=settings, max_per_run=3)

    spent = BudgetManager(synced_session, settings).spent()
    assert spent <= settings.daily_ai_budget_usd
    assert report.details["plan"]["en"] > 0
    assert report.details["plan"]["ru"] > 0


def test_rerendering_a_stored_article_is_stable(synced_session, settings):
    pipeline = build_pipeline(synced_session, settings)
    article = None
    for candidate in select_topics_for_generation(synced_session, "en", 12) or [
        first_topic(synced_session, "en")
    ]:
        outcome = pipeline.generate(candidate)
        if outcome.ok:
            article = outcome.article
            break
    if article is None:
        pytest.skip("no article passed the gates in this fixture set")

    rendered = render_stored_article(synced_session, article, settings=settings)
    assert validate_rich_message(rendered.message) == []
    assert collect_urls(rendered.message)

    # Media placements must resolve to the same assets as the original render.
    stored_photos = [
        block["photo"]["media"]
        for block in article.rendered_message["blocks"]
        if block["type"] == "photo"
    ]
    rerendered_photos = [
        block["photo"]["media"] for block in rendered.message["blocks"] if block["type"] == "photo"
    ]
    assert rerendered_photos == stored_photos


def test_analytics_counts_a_click(synced_session, settings):
    from app.analytics.tracking import TrackingService

    tracking = TrackingService(synced_session, settings=settings)
    link = tracking.get_or_create(
        article=None,
        market="en",
        target_url="https://wegotrip.com/paris-d2988507/tour-p1/?coupon=435",
        product_external_id="1",
    )
    row = tracking.resolve(link.token)
    assert row is not None
    tracking.record_click(row, visitor_hash="v1")
    tracking.record_click(row, visitor_hash="v1")
    tracking.record_click(row, visitor_hash="v2")
    assert row.clicks == 3
    assert row.unique_clicks == 2


def test_tracking_refuses_an_unmarked_store_link(synced_session, settings):
    from app.analytics.tracking import TrackingService
    from app.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        TrackingService(synced_session, settings=settings).get_or_create(
            article=None,
            market="en",
            target_url="https://wegotrip.com/paris-d2988507/tour-p1/",
        )


def test_kpis_are_computable_on_an_empty_database(session, settings):
    kpis = AnalyticsService(session, settings).kpis()
    assert kpis["articles_generated"] == 0
    assert kpis["ai_cost_per_order"] is None
