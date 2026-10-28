"""Daily destination diversity and RU domestic preference for topic selection."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterable, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import Market, Settings, get_settings
from app.db.enums import ArticleStatus
from app.db.models import Article, TopicCandidate
from app.db.types import utcnow
from app.logging_setup import get_logger
from app.topics.coverage import usable_candidate_query
from app.topics.geo import GeoResolver, TopicGeo

log = get_logger("topics.diversity")

#: Statuses that already occupy a publish slot for the local day.
_DAY_OCCUPYING = {
    ArticleStatus.SCHEDULED,
    ArticleStatus.PUBLISHING,
    ArticleStatus.PUBLISHED,
    ArticleStatus.APPROVED,
    ArticleStatus.NEEDS_REVIEW,
}


def _local_day_bounds(settings: Settings) -> tuple[dt.datetime, dt.datetime]:
    local_now = utcnow().astimezone(settings.publish_tz)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + dt.timedelta(days=1)
    return local_start.astimezone(dt.UTC), local_end.astimezone(dt.UTC)


def todays_articles(session: Session, market: Market, settings: Settings) -> list[Article]:
    start, end = _local_day_bounds(settings)
    return list(
        session.scalars(
            select(Article).where(
                Article.market == market,
                Article.status.in_(list(_DAY_OCCUPYING)),
                or_(
                    and_(Article.scheduled_for >= start, Article.scheduled_for < end),
                    and_(Article.published_at >= start, Article.published_at < end),
                    and_(
                        Article.scheduled_for.is_(None),
                        Article.published_at.is_(None),
                        Article.created_at >= start,
                        Article.created_at < end,
                    ),
                ),
            )
        ).all()
    )


class DiversityTracker:
    def __init__(
        self,
        *,
        max_same_city: int,
        max_same_attraction: int,
    ) -> None:
        self.max_same_city = max(1, max_same_city)
        self.max_same_attraction = max(1, max_same_attraction)
        self.city_counts: Counter[str] = Counter()
        self.attraction_counts: Counter[str] = Counter()

    def observe(self, geo: TopicGeo) -> None:
        if geo.city_id:
            self.city_counts[geo.city_id] += 1
        if geo.attraction_id:
            self.attraction_counts[geo.attraction_id] += 1

    def allows(self, geo: TopicGeo) -> bool:
        if (
            geo.attraction_id
            and self.attraction_counts[geo.attraction_id] >= self.max_same_attraction
        ):
            return False
        return not (geo.city_id and self.city_counts[geo.city_id] >= self.max_same_city)


def select_diverse_topics(
    session: Session,
    market: Market,
    limit: int,
    *,
    settings: Settings | None = None,
) -> list[TopicCandidate]:
    """Pick highest-scoring topics with city/attraction caps and RU preference.

    For ``market=ru`` the selector fills a domestic (Russia) share first when
    inventory exists, then tops up with other countries — still under the same
    per-city / per-attraction daily caps.
    """
    settings = settings or get_settings()
    if limit <= 0:
        return []

    pool_size = max(limit * 6, 40)
    pool = list(
        session.scalars(
            usable_candidate_query(market, settings)
            .order_by((TopicCandidate.topic_score + TopicCandidate.boost).desc())
            .limit(pool_size)
        ).all()
    )
    if not pool:
        return []

    resolver = GeoResolver(session, market)
    tracker = DiversityTracker(
        max_same_city=settings.max_same_city_per_day,
        max_same_attraction=settings.max_same_attraction_per_day,
    )
    for article in todays_articles(session, market, settings):
        tracker.observe(
            resolver.resolve(
                entity_type=article.entity_type,
                entity_external_id=article.entity_external_id,
            )
        )

    geos = {topic.id: resolver.resolve_topic(topic) for topic in pool}

    selected: list[TopicCandidate] = []

    def take_from(candidates: Iterable[TopicCandidate], remaining: int) -> None:
        for topic in candidates:
            if remaining <= 0:
                return
            geo = geos[topic.id]
            if not tracker.allows(geo):
                continue
            selected.append(topic)
            tracker.observe(geo)
            remaining -= 1

    if market == "ru" and settings.ru_prefer_domestic:
        domestic_quota = max(1, round(limit * settings.ru_domestic_share))
        domestic = [t for t in pool if geos[t.id].is_russia]
        foreign = [t for t in pool if not geos[t.id].is_russia]
        if domestic:
            take_from(domestic, min(domestic_quota, limit))
            take_from(foreign, limit - len(selected))
            # If foreign ran dry under caps, finish with more domestic.
            if len(selected) < limit:
                take_from(domestic, limit - len(selected))
        else:
            log.info(
                "topics.no_domestic_inventory",
                market=market,
                note="Russia preference skipped; catalogue has no usable RU-geo candidates",
            )
            take_from(pool, limit)
    else:
        take_from(pool, limit)

    log.info(
        "topics.diverse_selection",
        market=market,
        requested=limit,
        selected=len(selected),
        pool=len(pool),
        cities_used=len(tracker.city_counts),
        russia_selected=sum(1 for t in selected if geos[t.id].is_russia),
    )
    return selected


def order_articles_for_schedule(
    articles: Sequence[Article],
    session: Session,
    market: Market,
    *,
    settings: Settings,
) -> list[Article]:
    """Reorder a pending queue so the day's slots stay geographically diverse."""
    if not articles:
        return []
    resolver = GeoResolver(session, market)
    tracker = DiversityTracker(
        max_same_city=settings.max_same_city_per_day,
        max_same_attraction=settings.max_same_attraction_per_day,
    )
    for article in todays_articles(session, market, settings):
        # Already-scheduled/published for today occupy slots; pending ones in
        # ``articles`` are not yet assigned and must not pre-count here.
        if article.scheduled_for is None and article.published_at is None:
            continue
        tracker.observe(
            resolver.resolve(
                entity_type=article.entity_type,
                entity_external_id=article.entity_external_id,
            )
        )

    geos = {
        article.id: resolver.resolve(
            entity_type=article.entity_type,
            entity_external_id=article.entity_external_id,
        )
        for article in articles
    }

    preferred: list[Article] = []
    deferred: list[Article] = []

    def rank_key(article: Article) -> tuple[int, dt.datetime]:
        geo = geos[article.id]
        domestic = 0 if (market == "ru" and settings.ru_prefer_domestic and geo.is_russia) else 1
        return (domestic, article.created_at or utcnow())

    for article in sorted(articles, key=rank_key):
        geo = geos[article.id]
        if tracker.allows(geo):
            preferred.append(article)
            tracker.observe(geo)
        else:
            deferred.append(article)
    return preferred + deferred


__all__ = [
    "DiversityTracker",
    "order_articles_for_schedule",
    "select_diverse_topics",
    "todays_articles",
]
