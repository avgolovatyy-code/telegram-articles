"""Background jobs.

All jobs are idempotent and safe to re-run: catalog sync upserts, topic discovery
deduplicates, generation reserves budget before spending, and publication is guarded by
an idempotency key.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, func, or_, select
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
from app.max.publisher import maybe_publish_ru_to_max
from app.slack.notifications import SlackNotifier
from app.telegram.api import build_telegram_client
from app.telegram.publisher import TelegramPublisher
from app.topics.clusters import KeywordClusterRegistry
from app.topics.coverage import CoverageReport, assess_coverage
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
        coverage = assess_coverage(session, market, settings)
        report.details[market] = {**stats.as_dict(), "coverage": coverage.as_dict()}
        if coverage.exhausted:
            log.info("topics.exhausted", market=market, reason=coverage.reason)
    return report


def coverage_report(
    session: Session,
    *,
    markets: tuple[Market, ...] = MARKETS,
    settings: Settings | None = None,
) -> dict[str, CoverageReport]:
    """How much of the catalogue still has unwritten topics."""
    settings = settings or get_settings()
    return {market: assess_coverage(session, market, settings) for market in markets}


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
    notifier = SlackNotifier(session, settings)

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

        candidates = select_topics_for_generation(session, market, wanted * 3, settings=settings)
        if not candidates:
            # The daily target is a ceiling, not an obligation: with no topic above the
            # quality floor the engine stops rather than inventing something to write.
            coverage = assess_coverage(session, market, settings)
            report.details[f"{market}_generated"] = 0
            report.details[f"{market}_exhausted"] = coverage.reason
            log.info(
                "topics.exhausted",
                market=market,
                reason=coverage.reason,
                below_threshold=coverage.below_threshold,
                used_topics=coverage.used_topics,
                available_products=coverage.available_products,
            )
            continue

        # Do not generate more than public channels can still absorb today.
        publish_room = remaining_same_day_publish_slots(session, market, settings)
        awaiting_schedule = int(
            session.scalar(
                select(func.count(Article.id)).where(
                    Article.market == market,
                    Article.status.in_(
                        [ArticleStatus.APPROVED, ArticleStatus.NEEDS_REVIEW]
                    ),
                    Article.scheduled_for.is_(None),
                )
            )
            or 0
        )
        publish_room = max(0, publish_room - awaiting_schedule)
        if publish_room <= 0:
            report.details[f"{market}_generated"] = 0
            report.details[f"{market}_publish_capped"] = (
                "no same-day production slots left; skip generation to avoid backlog"
            )
            continue
        wanted = min(wanted, publish_room)
        report.details[f"{market}_publish_room"] = publish_room

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
                if outcome.article is not None:
                    notifier.article_drafted(outcome.article)
            else:
                skipped += 1
        report.details[f"{market}_generated"] = produced
        report.details[f"{market}_skipped"] = skipped
        if produced < wanted:
            coverage = assess_coverage(session, market, settings)
            if coverage.exhausted:
                report.details[f"{market}_exhausted"] = coverage.reason

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

            # The daily figure, when set, is a ceiling for the whole day rather than per
            # scheduler run: this job runs several times a day and must not multiply it.
            ceiling = settings.publish_per_day(market)
            if ceiling is None:
                wanted = len(pending)
            else:
                wanted = min(len(pending), ceiling - _planned_today(session, market, settings))
            if wanted <= 0:
                report.details[f"{market}_scheduled"] = 0
                report.details[f"{market}_note"] = "daily publication quota already planned"
                continue

            slots = _publication_slots(session, market, settings, count=wanted)
            scheduled = 0
            for article, slot in zip(pending, slots, strict=False):
                # Even in auto-publish mode the rendering is exercised on the test
                # channel first — production is never a preview mechanism (spec §40).
                if not any(p.target == PublicationTarget.TEST for p in article.publications):
                    if not settings.telegram_test_channel:
                        report.errors.append(
                            f"article {article.id}: TELEGRAM_TEST_CHANNEL is not configured"
                        )
                        continue
                    publisher.enqueue(
                        article, target=PublicationTarget.TEST, scheduled_for=utcnow()
                    )
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


def _planned_today(session: Session, market: Market, settings: Settings | None = None) -> int:
    """Articles already published or scheduled for publication on the local publish day."""
    settings = settings or get_settings()
    local_now = utcnow().astimezone(settings.publish_tz)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + dt.timedelta(days=1)
    start = local_start.astimezone(dt.UTC)
    end = local_end.astimezone(dt.UTC)
    return int(
        session.scalar(
            select(func.count(Article.id)).where(
                Article.market == market,
                or_(
                    and_(Article.scheduled_for >= start, Article.scheduled_for < end),
                    and_(Article.published_at >= start, Article.published_at < end),
                ),
            )
        )
        or 0
    )


def _publication_slots(
    session: Session, market: Market, settings: Settings, *, count: int
) -> list[dt.datetime]:
    """Spread ``count`` publications across the publishing window.

    Posts are distributed over the remaining window rather than fired back to back.
    Slots never jump ahead of a far-future backlog: only schedules inside the day
    currently being filled affect spacing. Overflow packs densely from the next
    morning — it does not append after a multi-day queue tail.
    """
    if count <= 0:
        return []

    now = utcnow()
    min_interval = dt.timedelta(minutes=settings.min_post_interval_minutes)
    cursor = _next_in_window(now + dt.timedelta(minutes=5), settings)

    slots: list[dt.datetime] = []
    remaining = count
    while remaining > 0:
        window_end = _window_end(cursor, settings)
        day_start = _window_start(cursor, settings)
        last_in_day = session.scalar(
            select(Article.scheduled_for)
            .where(
                Article.market == market,
                Article.scheduled_for.is_not(None),
                Article.scheduled_for >= day_start,
                Article.scheduled_for <= window_end,
            )
            .order_by(Article.scheduled_for.desc())
            .limit(1)
        )
        # Also respect a post that just went out / is imminent before day_start.
        last_recent = session.scalar(
            select(Article.scheduled_for)
            .where(
                Article.market == market,
                Article.scheduled_for.is_not(None),
                Article.scheduled_for >= now - min_interval,
                Article.scheduled_for < day_start,
            )
            .order_by(Article.scheduled_for.desc())
            .limit(1)
        )
        earliest = cursor
        for prior in (last_in_day, last_recent):
            if prior is not None:
                earliest = max(earliest, prior + min_interval)
        cursor = _next_in_window(earliest, settings)
        if cursor > window_end:
            cursor = _next_in_window(window_end + dt.timedelta(minutes=1), settings)
            continue

        available = window_end - cursor
        fits_today = min(remaining, int(available / min_interval) + 1)
        if fits_today <= 0:
            cursor = _next_in_window(window_end + dt.timedelta(minutes=1), settings)
            continue
        if fits_today <= 1:
            spacing = min_interval
        else:
            # Stretch across the remaining window; never tighter than the minimum.
            spacing = max(min_interval, available / (fits_today - 1))

        day_slots = [cursor + spacing * index for index in range(fits_today)]
        slots.extend(day_slots)
        remaining -= fits_today
        cursor = _next_in_window(window_end + dt.timedelta(minutes=1), settings)

    return slots


def remaining_same_day_publish_slots(
    session: Session, market: Market, settings: Settings
) -> int:
    """How many more production posts can still go out today (Moscow window).

    Used to stop generating more articles than the public channels can absorb the
    same calendar day — so the test channel does not run ahead of production.
    """
    now = utcnow()
    local = now.astimezone(settings.publish_tz)
    if local.hour >= settings.publish_window_end_hour:
        return 0

    min_interval = dt.timedelta(minutes=settings.min_post_interval_minutes)
    cursor = _next_in_window(now + dt.timedelta(minutes=5), settings)
    window_end = _window_end(cursor, settings)
    # If we were snapped into tomorrow (should not happen before end hour), no same-day room.
    if cursor.astimezone(settings.publish_tz).date() != local.date():
        return 0

    day_start = _window_start(cursor, settings)
    last_in_day = session.scalar(
        select(Article.scheduled_for)
        .where(
            Article.market == market,
            Article.scheduled_for.is_not(None),
            Article.scheduled_for >= day_start,
            Article.scheduled_for <= window_end,
        )
        .order_by(Article.scheduled_for.desc())
        .limit(1)
    )
    if last_in_day is not None:
        cursor = _next_in_window(max(cursor, last_in_day + min_interval), settings)
    if cursor > window_end:
        return 0
    available = window_end - cursor
    return int(available / min_interval) + 1


def _window_start(moment: dt.datetime, settings: Settings) -> dt.datetime:
    """Start of the publishing window for the local day ``moment`` falls in."""
    local = moment.astimezone(settings.publish_tz)
    start = settings.publish_window_start_hour
    local_start = local.replace(hour=start, minute=0, second=0, microsecond=0)
    return local_start.astimezone(dt.UTC)


def _window_end(moment: dt.datetime, settings: Settings) -> dt.datetime:
    """End of the publishing window for the local day ``moment`` falls in."""
    local = moment.astimezone(settings.publish_tz)
    start, end = settings.publish_window_start_hour, settings.publish_window_end_hour
    if start >= end:
        local_end = local.replace(hour=23, minute=59, second=0, microsecond=0)
    else:
        local_end = local.replace(hour=end, minute=0, second=0, microsecond=0)
    return local_end.astimezone(dt.UTC)


def _next_in_window(moment: dt.datetime, settings: Settings) -> dt.datetime:
    """Move ``moment`` forward to the next instant inside the publishing window.

    Window hours are local to ``PUBLISH_TIMEZONE`` (Moscow by default) while everything
    stored in the database stays UTC, so the window follows daylight-saving changes in
    other timezones without any date arithmetic elsewhere.
    """
    start, end = settings.publish_window_start_hour, settings.publish_window_end_hour
    if start >= end:
        return moment

    local = moment.astimezone(settings.publish_tz)
    if local.hour < start:
        local = local.replace(hour=start, minute=0, second=0, microsecond=0)
    elif local.hour >= end:
        local = (local + dt.timedelta(days=1)).replace(
            hour=start, minute=0, second=0, microsecond=0
        )
    return local.astimezone(dt.UTC)


# ----------------------------------------------------------------- publishing
def process_publication_queue(
    session: Session, *, settings: Settings | None = None, limit: int = 5
) -> JobReport:
    settings = settings or get_settings()
    report = JobReport("process_publication_queue")
    worker_id = new_job_id("pub")
    client = build_telegram_client(settings)
    publisher = TelegramPublisher(session, client, settings=settings)
    notifier = SlackNotifier(session, settings)

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
                        if item.target == PublicationTarget.PRODUCTION:
                            notifier.article_published(
                                article,
                                message_url=result.publication.message_url,
                                channel=result.publication.channel_username,
                            )
                            if article.market == "ru":
                                max_result = maybe_publish_ru_to_max(
                                    article, settings=settings
                                )
                                ctx["max"] = (
                                    "skipped"
                                    if max_result.skipped
                                    else ("ok" if max_result.ok else max_result.error)
                                )
                                if max_result.error:
                                    report.details.setdefault("max_errors", []).append(
                                        f"article {article.id}: {max_result.error}"
                                    )
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


def send_daily_digest(session: Session, *, settings: Settings | None = None) -> JobReport:
    """Post the daily summary to Slack."""
    settings = settings or get_settings()
    report = JobReport("send_daily_digest")
    notifier = SlackNotifier(session, settings)
    if not notifier.enabled:
        report.details["skipped"] = "Slack is not configured"
        return report
    notifier.daily_digest()
    report.details["sent"] = True
    return report


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
    "coverage_report",
    "discover_topics",
    "generate_daily_articles",
    "process_publication_queue",
    "refresh_article_products",
    "remaining_same_day_publish_slots",
    "run_daily_cycle",
    "schedule_publications",
    "seed_reference_data",
    "send_daily_digest",
    "sync_catalog",
]
