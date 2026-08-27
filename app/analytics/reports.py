"""Reporting queries for the dashboard and the topic feedback loop."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MARKETS, Market, Settings, get_settings
from app.db.enums import ArticleStatus, TopicStatus
from app.db.models import (
    Article,
    Attraction,
    City,
    ClickEvent,
    Collection,
    ConversionEvent,
    CostLedgerEntry,
    Country,
    Product,
    TopicCandidate,
    TrackingLink,
)
from app.db.types import utcnow


@dataclass(slots=True)
class MarketOverview:
    market: str
    countries: int = 0
    cities: int = 0
    attractions: int = 0
    collections: int = 0
    products: int = 0
    new_products_7d: int = 0
    topic_candidates: int = 0
    drafts: int = 0
    scheduled: int = 0
    published_today: int = 0
    published_total: int = 0
    validation_failures: int = 0
    generated_today: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArticlePerformance:
    article_id: int
    public_id: str
    market: str
    title: str
    primary_query: str
    published_at: dt.datetime | None
    clicks: int = 0
    unique_clicks: int = 0
    orders: int = 0
    gmv: float = 0.0
    revenue: float = 0.0
    ai_cost_usd: float = 0.0

    @property
    def conversion_rate(self) -> float:
        return round(self.orders / self.clicks, 4) if self.clicks else 0.0

    @property
    def revenue_per_article(self) -> float:
        return round(self.revenue, 4)

    @property
    def ai_cost_per_order(self) -> float | None:
        return round(self.ai_cost_usd / self.orders, 4) if self.orders else None


@dataclass(slots=True)
class DashboardData:
    budget: dict[str, Any]
    markets: list[MarketOverview] = field(default_factory=list)
    recent_articles: list[Article] = field(default_factory=list)
    top_topics: list[TopicCandidate] = field(default_factory=list)
    kpis: dict[str, Any] = field(default_factory=dict)


class AnalyticsService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # ------------------------------------------------------------- overviews
    def market_overview(self, market: Market) -> MarketOverview:
        start_of_day = dt.datetime.combine(utcnow().date(), dt.time.min, tzinfo=dt.UTC)
        week_ago = utcnow() - dt.timedelta(days=7)

        def count(model: Any, *conditions: Any) -> int:
            return int(
                self.session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
            )

        return MarketOverview(
            market=market,
            countries=count(Country, Country.market == market),
            cities=count(City, City.market == market),
            attractions=count(Attraction, Attraction.market == market),
            collections=count(Collection, Collection.market == market),
            products=count(Product, Product.market == market, Product.available.is_(True)),
            new_products_7d=count(
                Product, Product.market == market, Product.created_at >= week_ago
            ),
            topic_candidates=count(
                TopicCandidate,
                TopicCandidate.market == market,
                TopicCandidate.status == TopicStatus.CANDIDATE,
            ),
            drafts=count(
                Article,
                Article.market == market,
                Article.status.in_([ArticleStatus.DRAFT, ArticleStatus.NEEDS_REVIEW]),
            ),
            scheduled=count(
                Article,
                Article.market == market,
                Article.status.in_([ArticleStatus.SCHEDULED, ArticleStatus.APPROVED]),
            ),
            published_today=count(
                Article,
                Article.market == market,
                Article.status == ArticleStatus.PUBLISHED,
                Article.published_at >= start_of_day,
            ),
            published_total=count(
                Article, Article.market == market, Article.status == ArticleStatus.PUBLISHED
            ),
            validation_failures=count(
                Article,
                Article.market == market,
                Article.status == ArticleStatus.VALIDATION_FAILED,
            ),
            generated_today=count(
                Article, Article.market == market, Article.created_at >= start_of_day
            ),
        )

    def overviews(self) -> list[MarketOverview]:
        return [self.market_overview(market) for market in MARKETS]

    # -------------------------------------------------------------- spending
    def spend_by_day(self, days: int = 14) -> list[tuple[dt.date, float]]:
        since = utcnow().date() - dt.timedelta(days=days)
        rows = self.session.execute(
            select(CostLedgerEntry.spend_date, func.sum(CostLedgerEntry.amount_usd))
            .where(CostLedgerEntry.spend_date >= since)
            .group_by(CostLedgerEntry.spend_date)
            .order_by(CostLedgerEntry.spend_date)
        ).all()
        return [(row[0], round(float(row[1] or 0.0), 4)) for row in rows]

    def spend_by_market_today(self) -> dict[str, float]:
        today = utcnow().date()
        rows = self.session.execute(
            select(CostLedgerEntry.market, func.sum(CostLedgerEntry.amount_usd))
            .where(CostLedgerEntry.spend_date == today)
            .group_by(CostLedgerEntry.market)
        ).all()
        return {str(row[0] or "shared"): round(float(row[1] or 0.0), 4) for row in rows}

    # ----------------------------------------------------------- performance
    def article_performance(self, *, limit: int = 50) -> list[ArticlePerformance]:
        articles = list(
            self.session.scalars(
                select(Article)
                .where(Article.status == ArticleStatus.PUBLISHED)
                .order_by(Article.published_at.desc())
                .limit(limit)
            ).all()
        )
        if not articles:
            return []
        ids = [article.id for article in articles]

        click_rows = self.session.execute(
            select(
                TrackingLink.article_id,
                func.sum(TrackingLink.clicks),
                func.sum(TrackingLink.unique_clicks),
            )
            .where(TrackingLink.article_id.in_(ids))
            .group_by(TrackingLink.article_id)
        ).all()
        clicks = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in click_rows}

        conversion_rows = self.session.execute(
            select(
                ConversionEvent.article_id,
                func.count(ConversionEvent.id),
                func.sum(ConversionEvent.gmv),
                func.sum(ConversionEvent.revenue),
            )
            .where(ConversionEvent.article_id.in_(ids))
            .group_by(ConversionEvent.article_id)
        ).all()
        conversions = {
            row[0]: (int(row[1] or 0), float(row[2] or 0.0), float(row[3] or 0.0))
            for row in conversion_rows
        }

        out: list[ArticlePerformance] = []
        for article in articles:
            click_count, unique_count = clicks.get(article.id, (0, 0))
            orders, gmv, revenue = conversions.get(article.id, (0, 0.0, 0.0))
            out.append(
                ArticlePerformance(
                    article_id=article.id,
                    public_id=article.public_id,
                    market=article.market,
                    title=article.title or article.primary_query,
                    primary_query=article.primary_query,
                    published_at=article.published_at,
                    clicks=click_count,
                    unique_clicks=unique_count,
                    orders=orders,
                    gmv=round(gmv, 2),
                    revenue=round(revenue, 2),
                    ai_cost_usd=round(article.actual_cost_usd, 6),
                )
            )
        return out

    def kpis(self) -> dict[str, Any]:
        total_articles = int(self.session.scalar(select(func.count(Article.id))) or 0)
        published = int(
            self.session.scalar(
                select(func.count(Article.id)).where(Article.status == ArticleStatus.PUBLISHED)
            )
            or 0
        )
        clicks = int(
            self.session.scalar(select(func.coalesce(func.sum(TrackingLink.clicks), 0))) or 0
        )
        unique_clicks = int(
            self.session.scalar(select(func.coalesce(func.sum(TrackingLink.unique_clicks), 0))) or 0
        )
        orders = int(self.session.scalar(select(func.count(ConversionEvent.id))) or 0)
        gmv = float(
            self.session.scalar(select(func.coalesce(func.sum(ConversionEvent.gmv), 0.0))) or 0.0
        )
        revenue = float(
            self.session.scalar(select(func.coalesce(func.sum(ConversionEvent.revenue), 0.0)))
            or 0.0
        )
        ai_cost = float(
            self.session.scalar(select(func.coalesce(func.sum(CostLedgerEntry.amount_usd), 0.0)))
            or 0.0
        )
        return {
            "articles_generated": total_articles,
            "articles_published": published,
            "clicks": clicks,
            "unique_clicks": unique_clicks,
            "orders": orders,
            "gmv": round(gmv, 2),
            "revenue": round(revenue, 2),
            "conversion_rate": round(orders / clicks, 4) if clicks else 0.0,
            "revenue_per_article": round(revenue / published, 4) if published else 0.0,
            "ai_cost_total_usd": round(ai_cost, 4),
            "ai_cost_per_article": round(ai_cost / total_articles, 6) if total_articles else 0.0,
            "ai_cost_per_order": round(ai_cost / orders, 4) if orders else None,
        }

    # ------------------------------------------------------- feedback signals
    def entity_performance(self, market: Market) -> dict[str, float]:
        """Revenue-weighted score per entity, used to bias future topic scoring."""
        rows = self.session.execute(
            select(
                Article.entity_external_id,
                func.count(ConversionEvent.id),
                func.coalesce(func.sum(ConversionEvent.revenue), 0.0),
                func.coalesce(func.sum(TrackingLink.clicks), 0),
            )
            .select_from(Article)
            .outerjoin(ConversionEvent, ConversionEvent.article_id == Article.id)
            .outerjoin(TrackingLink, TrackingLink.article_id == Article.id)
            .where(Article.market == market, Article.status == ArticleStatus.PUBLISHED)
            .group_by(Article.entity_external_id)
        ).all()

        scores: dict[str, float] = {}
        for entity_id, orders, revenue, clicks in rows:
            if not entity_id:
                continue
            signal = 0.0
            if clicks:
                signal += min(1.0, float(clicks) / 200.0) * 0.4
            if orders:
                signal += min(1.0, float(orders) / 10.0) * 0.6
            if revenue:
                signal = max(signal, min(1.0, float(revenue) / 500.0))
            scores[entity_id] = round(signal, 4)
        return scores

    def recent_click_events(self, limit: int = 50) -> list[ClickEvent]:
        return list(
            self.session.scalars(
                select(ClickEvent).order_by(ClickEvent.created_at.desc()).limit(limit)
            ).all()
        )


__all__ = ["AnalyticsService", "ArticlePerformance", "DashboardData", "MarketOverview"]
