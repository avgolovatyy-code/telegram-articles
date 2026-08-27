"""Background jobs.

All jobs are idempotent and safe to re-run: catalog sync upserts, topic discovery
deduplicates, generation reserves budget before spending, and publication is guarded by
an idempotency key.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.budget import BudgetManager
from app.ai.prompts import sync_prompt_versions
from app.ai.router import LLMGateway
from app.catalog import build_catalog_provider
from app.catalog.sync import CatalogSyncService, SyncOptions, refresh_product
from app.config import MARKETS, Market, Settings, get_settings
from app.db.base import session_scope
from app.db.enums import ArticleStatus, PublicationStatus, PublicationTarget
from app.db.models import Article, ArticleProduct, Product, PublicationQueueItem
from app.db.models import Market as MarketRow
from app.db.types import utcnow
from app.errors import EngineError, TelegramRateLimited
from app.generation.pipeline import GenerationPipeline
from app.logging_setup import get_logger, job_context, new_job_id
from app.telegram.api import build_telegram_client
from app.telegram.publisher import TelegramPublisher
from app.topics.clusters import KeywordClusterRegistry
from app.topics.discovery import TopicDiscoveryService, select_topics_for_generation

log = get_logger("scheduler.jobs")


@dataclass(slots=True)
class JobReport:
    name: str
    ok: bool = True
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ bootstrap
def seed_reference_data(session: Session, settings: Settings | None = None) -> JobReport:
    """Idempotently create market rows, keyword clusters and prompt versions."""
    settings = settings or get_settings()
    report = JobReport("seed")

    for market in MARKETS:
        row = session.get(MarketRow, market)
        if row is None:
            row = MarketRow(
                code=market,
                language="Russian" if market == "ru" else "English",
                store_domain=settings.store_domain(market),
                currency_code=settings.currency(market),
                telegram_channel=settings.telegram_channel(market),
            )
            session.add(row)
        else:
            row.store_domain = settings.store_domain(market)
            row.currency_code = settings.currency(market)
            row.telegram_channel = settings.telegram_channel(market)

    report.details["clusters"] = KeywordClusterRegistry(session).sync_seeds()
    report.details["prompts"] = sync_prompt_versions(session)
    session.flush()
    return report


# --------------------------------------------------------------------- catalog
def sync_catalog(
    session: Session,
    *,
    markets: tuple[Market, ...] = MARKETS,
    options: SyncOptions | None = None,
    settings: Settings | None = None,
) -> JobReport:
    settings = settings or get_settings()
    provider = build_catalog_provider(settings)
    service = CatalogSyncService(session, provider, settings=settings)
    report = JobReport("sync_catalog")
    try:
        for market in markets:
            stats = service.sync_market(market, options)
            report.details[market] = stats.as_dict()
            report.errors.extend(stats.errors)
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()
    report.ok = not report.errors
    return report


def refresh_article_products(
    session: Session, article: Article, *, settings: Settings | None = None
) -> list[str]:
    """Re-read product data from the API right before publication (spec §36).

    Returns the ids of products that disappeared or became unavailable.
    """
    settings = settings or get_settings()
    provider = build_catalog_provider(settings)
    market: Market = article.market  # type: ignore[assignment]
    stale: list[str] = []
    try:
        for link in article.products:
            product = refresh_product(
                session, provider, market, link.product_external_id, settings=settings
            )
            if product is None or not product.available or not product.published:
                stale.append(link.product_external_id)
                link.active = False
            else:
                link.snapshot = {
                    "title": product.title,
                    "price": product.price,
                    "currency": product.currency_code,
                    "rating": product.rating,
                    "available": product.available,
                    "snapshot_id": product.snapshot_id,
                }
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()
    article.products_refreshed_at = utcnow()
    session.flush()
    return stale


# ---------------------------------------------------------------------- topics
def discover_topics(
    session: Session,
    *,
    markets: tuple[Market, ...] = MARKETS,
    limit: int | None = None,
    settings: Settings | None = None,
) -> JobReport:
    settings = settings or get_settings()
    service = TopicDiscoveryService(session, settings=settings)
    report = JobReport("discover_topics")
    for market in markets:
        stats = service.discover(market, limit=limit)
        report.details[market] = stats.as_dict()
    return report


# ------------------------------------------------------------------ generation
def generate_daily_articles(
    session: Session,
    *,
    markets: tuple[Market, ...] = MARKETS,
    settings: Settings | None = None,
    max_per_run: int | None = None,
) -> JobReport:
    """Generate as many articles as the budget plan allows, minimums first."""
    settings = settings or get_settings()
    report = JobReport("generate_daily_articles")
    budget = BudgetManager(session, settings)
    gateway = LLMGateway(session, settings=settings, budget=budget)
    pipeline = GenerationPipeline(session, gateway, settings=settings)

    plan = budget.plan_daily_generation()
    report.details["plan"] = plan

    for market in markets:
        wanted = plan.get(market, 0)
        if max_per_run is not None:
            wanted = min(wanted, max_per_run)
        produced = 0
        skipped = 0
        if wanted <= 0:
            report.details[f"{market}_generated"] = 0
            continue

        candidates = select_topics_for_generation(session, market, wanted * 3)
        for topic in candidates:
            if produced >= wanted:
                break
            decision = budget.can_start_article(market)
            if not decision.allowed:
                report.details[f"{market}_stopped"] = decision.reason
                break
            try:
                outcome = pipeline.generate(topic)
            except EngineError as exc:
                report.errors.append(f"{market}/{topic.id}: {exc}")
                log.error("job.generate_failed", market=market, topic_id=topic.id, error=str(exc))
                continue
            if outcome.ok:
                produced += 1
            else:
                skipped += 1
        report.details[f"{market}_generated"] = produced
        report.details[f"{market}_skipped"] = skipped

    snapshot = budget.snapshot()
    report.details["budget"] = {
        "date": snapshot.spend_date.isoformat(),
        "budget_usd": snapshot.budget_usd,
        "spent_usd": snapshot.spent_usd,
        "reserved_usd": snapshot.reserved_usd,
        "remaining_usd": snapshot.remaining_usd,
        "generated": snapshot.generated,
        "average_article_cost_usd": snapshot.average_article_cost_usd,
    }
    report.ok = not report.errors
    return report


# ----------------------------------------------------------------- scheduling
def schedule_publications(
    session: Session,
    *,
    markets: tuple[Market, ...] = MARKETS,
    settings: Settings | None = None,
) -> JobReport:
    """Spread approved articles evenly across the publishing window (spec §35)."""
    settings = settings or get_settings()
    report = JobReport("schedule_publications")
    client = build_telegram_client(settings)
    publisher = TelegramPublisher(session, client, settings=settings)

    try:
        for market in markets:
            statuses = [ArticleStatus.APPROVED]
            if settings.auto_publish(market):
                statuses.append(ArticleStatus.NEEDS_REVIEW)
            pending = list(
                session.scalars(
                    select(Article)
                    .where(
                        Article.market == market,
                        Article.status.in_(statuses),
                        Article.scheduled_for.is_(None),
                    )
                    .order_by(Article.created_at)
                ).all()
            )
            if not pending:
                report.details[f"{market}_scheduled"] = 0
                continue

            slots = _publication_slots(
                session, market, settings, count=min(len(pending), settings.publish_per_day(market))
            )
            scheduled = 0
            for article, slot in zip(pending, slots, strict=False):
                article.scheduled_for = slot
                article.status = ArticleStatus.SCHEDULED
                publisher.enqueue(article, target=PublicationTarget.PRODUCTION, scheduled_for=slot)
                scheduled += 1
            report.details[f"{market}_scheduled"] = scheduled
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    session.flush()
    return report


def _publication_slots(
    session: Session, market: Market, settings: Settings, *, count: int
) -> list[dt.datetime]:
    now = utcnow()
    interval = dt.timedelta(minutes=settings.min_post_interval_minutes)

    last = session.scalar(
        select(Article.scheduled_for)
        .where(
            Article.market == market,
            Article.scheduled_for.is_not(None),
            Article.scheduled_for >= now - interval,
        )
        .order_by(Article.scheduled_for.desc())
        .limit(1)
    )
    cursor = max(now + dt.timedelta(minutes=5), (last + interval) if last else now)

    slots: list[dt.datetime] = []
    while len(slots) < count:
        cursor = _next_in_window(cursor, settings)
        slots.append(cursor)
        cursor = cursor + interval
    return slots


def _next_in_window(moment: dt.datetime, settings: Settings) -> dt.datetime:
    start, end = settings.publish_window_start_hour, settings.publish_window_end_hour
    if start >= end:
        return moment
    if moment.hour < start:
        return moment.replace(hour=start, minute=0, second=0, microsecond=0)
    if moment.hour >= end:
        return (moment + dt.timedelta(days=1)).replace(
            hour=start, minute=0, second=0, microsecond=0
        )
    return moment


# ----------------------------------------------------------------- publishing
def process_publication_queue(
    session: Session, *, settings: Settings | None = None, limit: int = 5
) -> JobReport:
    settings = settings or get_settings()
    report = JobReport("process_publication_queue")
    worker_id = new_job_id("pub")
    client = build_telegram_client(settings)
    publisher = TelegramPublisher(session, client, settings=settings)

    due = list(
        session.scalars(
            select(PublicationQueueItem)
            .where(
                PublicationQueueItem.status == PublicationStatus.PENDING,
                PublicationQueueItem.scheduled_for <= utcnow(),
            )
            .order_by(PublicationQueueItem.scheduled_for)
            .limit(limit)
        ).all()
    )

    published = 0
    try:
        for item in due:
            article = session.get(Article, item.article_id)
            if article is None or article.rendered_message is None:
                item.status = PublicationStatus.FAILED
                item.last_error = "article or rendered payload missing"
                continue
            with job_context(
                "publication.publish",
                job_id=worker_id,
                article_id=article.id,
                market=article.market,
            ) as ctx:
                try:
                    _ensure_fresh(session, article, settings)
                    result = publisher.publish(
                        article,
                        article.rendered_message,
                        target=item.target,
                        queue_item=item,
                        worker_id=worker_id,
                    )
                    if result.created:
                        published += 1
                    ctx["status"] = "published" if result.created else "already_published"
                except TelegramRateLimited as exc:
                    item.scheduled_for = utcnow() + dt.timedelta(seconds=exc.retry_after)
                    report.errors.append(f"rate limited, retry in {exc.retry_after}s")
                    ctx["status"] = "rate_limited"
                except EngineError as exc:
                    report.errors.append(f"article {article.id}: {exc}")
                    ctx["status"] = "error"
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    report.details["published"] = published
    report.details["considered"] = len(due)
    report.ok = not report.errors
    return report


def _ensure_fresh(session: Session, article: Article, settings: Settings) -> None:
    """Re-read products (and drop dead ones) if the draft is older than the threshold."""
    threshold = dt.timedelta(hours=settings.stale_article_refresh_hours)
    if article.products_refreshed_at and utcnow() - article.products_refreshed_at < threshold:
        return
    stale = refresh_article_products(session, article, settings=settings)
    if not stale:
        return
    log.warning("publication.stale_products", article_id=article.id, products=stale)
    _rerender_without(session, article, stale, settings)


def _rerender_without(
    session: Session, article: Article, stale_ids: list[str], settings: Settings
) -> None:
    """Rebuild the payload without products that disappeared from the catalogue."""
    from app.generation.schemas import ArticleDocument
    from app.services.rendering import render_stored_article

    if not article.body:
        return
    document = ArticleDocument.model_validate(article.body)
    document.product_placements = [
        placement
        for placement in document.product_placements
        if placement.product_id not in stale_ids
    ]
    article.body = document.model_dump()
    rendered = render_stored_article(session, article, settings=settings)
    article.rendered_message = rendered.message
    session.flush()


def cleanup_expired(session: Session, *, settings: Settings | None = None) -> JobReport:
    settings = settings or get_settings()
    report = JobReport("cleanup")
    report.details["reservations_released"] = BudgetManager(
        session, settings
    ).expire_stale_reservations()

    orphan_links = session.scalars(
        select(ArticleProduct).where(ArticleProduct.active.is_(True))
    ).all()
    dead = 0
    for link in orphan_links:
        article = session.get(Article, link.article_id)
        if article is None:
            continue
        product = session.scalar(
            select(Product).where(
                Product.market == article.market,
                Product.external_id == link.product_external_id,
            )
        )
        if product is None or not product.available:
            link.active = False
            dead += 1
    report.details["deactivated_product_links"] = dead
    session.flush()
    return report


def run_daily_cycle(settings: Settings | None = None) -> list[JobReport]:
    """Sync → discover → generate → schedule, in one transaction per step."""
    settings = settings or get_settings()
    reports: list[JobReport] = []
    for step in (sync_catalog, discover_topics, generate_daily_articles, schedule_publications):
        with session_scope() as session:
            reports.append(step(session, settings=settings))
    return reports


__all__ = [
    "JobReport",
    "cleanup_expired",
    "discover_topics",
    "generate_daily_articles",
    "process_publication_queue",
    "refresh_article_products",
    "run_daily_cycle",
    "schedule_publications",
    "seed_reference_data",
    "sync_catalog",
]
