"""ORM models.

Catalog entities are stored per market: the same WeGoTrip identifier appears in both
the EN and the RU catalogue with different names, media counts and product depth, so
every catalog table is keyed by ``(market, external_id)``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONColumn, UTCDateTime, utcnow


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


# --------------------------------------------------------------------- markets
class Market(Base, TimestampMixin):
    __tablename__ = "markets"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    store_domain: Mapped[str] = mapped_column(String(128), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    telegram_channel: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# --------------------------------------------------------------------- catalog
class Country(Base, TimestampMixin):
    __tablename__ = "countries"
    __table_args__ = (UniqueConstraint("market", "external_id", name="uq_countries_market_ext"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str | None] = mapped_column(String(8))
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    media: Mapped[list[dict[str, Any]]] = mapped_column(JSONColumn, default=list)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    city_count: Mapped[int] = mapped_column(Integer, default=0)
    popularity_rank: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class City(Base, TimestampMixin):
    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("market", "external_id", name="uq_cities_market_ext"),
        Index("ix_cities_market_product_count", "market", "product_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_external_id: Mapped[str | None] = mapped_column(String(64), index=True)
    country_name: Mapped[str | None] = mapped_column(String(255))
    popular: Mapped[bool] = mapped_column(Boolean, default=False)
    media: Mapped[list[dict[str, Any]]] = mapped_column(JSONColumn, default=list)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    attraction_count: Mapped[int] = mapped_column(Integer, default=0)
    popularity_rank: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Attraction(Base, TimestampMixin):
    __tablename__ = "attractions"
    __table_args__ = (
        UniqueConstraint("market", "external_id", name="uq_attractions_market_ext"),
        Index("ix_attractions_market_city", "market", "city_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city_external_id: Mapped[str | None] = mapped_column(String(64))
    country_external_id: Mapped[str | None] = mapped_column(String(64))
    preview: Mapped[str | None] = mapped_column(Text)
    media: Mapped[list[dict[str, Any]]] = mapped_column(JSONColumn, default=list)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    popularity_rank: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Category(Base, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("market", "external_id", name="uq_categories_market_ext"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Collection(Base, TimestampMixin):
    """Normalized subcategory (spec §4: ``Collection = normalized subcategory``)."""

    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("market", "external_id", name="uq_collections_market_ext"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="subcategory", nullable=False)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("market", "external_id", name="uq_products_market_ext"),
        Index("ix_products_market_city", "market", "city_external_id"),
        Index("ix_products_market_available", "market", "available"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str | None] = mapped_column(String(8))

    description: Mapped[str | None] = mapped_column(Text)
    short_description: Mapped[str | None] = mapped_column(Text)
    highlights: Mapped[list[str]] = mapped_column(JSONColumn, default=list)

    cover: Mapped[str | None] = mapped_column(Text)
    preview: Mapped[str | None] = mapped_column(Text)
    images: Mapped[list[dict[str, Any]]] = mapped_column(JSONColumn, default=list)
    audio_preview_url: Mapped[str | None] = mapped_column(Text)

    price: Mapped[float | None] = mapped_column(Float)
    exprice: Mapped[float | None] = mapped_column(Float)
    currency_code: Mapped[str | None] = mapped_column(String(8))
    currency_symbol: Mapped[str | None] = mapped_column(String(8))
    rating: Mapped[float | None] = mapped_column(Float)
    reviews_count: Mapped[int | None] = mapped_column(Integer)
    ratings_count: Mapped[int | None] = mapped_column(Integer)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    duration_max: Mapped[int | None] = mapped_column(Integer)
    duration_text: Mapped[str | None] = mapped_column(String(128))
    distance: Mapped[str | None] = mapped_column(String(64))

    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    types: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    tags: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    inclusions: Mapped[list[str]] = mapped_column(JSONColumn, default=list)
    exclusions: Mapped[list[str]] = mapped_column(JSONColumn, default=list)
    important_info: Mapped[list[str]] = mapped_column(JSONColumn, default=list)
    address: Mapped[str | None] = mapped_column(Text)
    start_location: Mapped[str | None] = mapped_column(Text)
    location_geo: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)

    country_external_id: Mapped[str | None] = mapped_column(String(64), index=True)
    city_external_id: Mapped[str | None] = mapped_column(String(64))
    primary_category: Mapped[str | None] = mapped_column(String(255))
    reviews: Mapped[list[dict[str, Any]]] = mapped_column(JSONColumn, default=list)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    popularity_rank: Mapped[int | None] = mapped_column(Integer)

    detail_fetched_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    api_updated_at: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    snapshot_id: Mapped[str | None] = mapped_column(String(64))

    categories: Mapped[list[ProductCategory]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    collections: Mapped[list[ProductCollection]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    attractions: Mapped[list[ProductAttraction]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    media_items: Mapped[list[ProductMedia]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )


class ProductCategory(Base):
    __tablename__ = "product_categories"
    __table_args__ = (
        UniqueConstraint("product_id", "category_external_id", name="uq_product_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(255))

    product: Mapped[Product] = relationship(back_populates="categories")


class ProductCollection(Base):
    __tablename__ = "product_collections"
    __table_args__ = (
        UniqueConstraint("product_id", "collection_external_id", name="uq_product_collection"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(255))

    product: Mapped[Product] = relationship(back_populates="collections")


class ProductAttraction(Base):
    __tablename__ = "product_attractions"
    __table_args__ = (
        UniqueConstraint("product_id", "attraction_external_id", name="uq_product_attraction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attraction_external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(255))

    product: Mapped[Product] = relationship(back_populates="attractions")


class ProductMedia(Base):
    __tablename__ = "product_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default="photo", nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    preview_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="media_items")


class CatalogSnapshot(Base):
    """Immutable record of what the Affiliate API returned for auditing claims."""

    __tablename__ = "catalog_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONColumn, nullable=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------- search intent
class KeywordCluster(Base, TimestampMixin):
    """A configurable set of query patterns for one entity type × market × intent."""

    __tablename__ = "keyword_clusters"
    __table_args__ = (
        UniqueConstraint("market", "entity_type", "intent", name="uq_keyword_cluster"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    primary_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    secondary_patterns: Mapped[list[str]] = mapped_column(JSONColumn, default=list)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    min_inventory: Mapped[int] = mapped_column(Integer, default=1)
    requires_volatile_facts: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class QueryCandidate(Base, TimestampMixin):
    __tablename__ = "query_candidates"
    __table_args__ = (
        UniqueConstraint("market", "canonical_query", name="uq_query_candidate_canonical"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_query: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    demand_score: Mapped[float | None] = mapped_column(Float)
    demand_source: Mapped[str] = mapped_column(String(32), default="heuristic", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class SearchDemandSnapshot(Base):
    __tablename__ = "search_demand_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer)
    trend: Mapped[float | None] = mapped_column(Float)
    competition: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    captured_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------- topics
class TopicCandidate(Base, TimestampMixin):
    __tablename__ = "topic_candidates"
    __table_args__ = (
        UniqueConstraint("market", "topic_key", name="uq_topic_candidate_key"),
        Index("ix_topic_candidates_market_status_score", "market", "status", "topic_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    topic_key: Mapped[str] = mapped_column(String(255), nullable=False)
    topic_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_query: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_query: Mapped[str] = mapped_column(Text, nullable=False)
    secondary_queries: Mapped[list[str]] = mapped_column(JSONColumn, default=list)
    relevant_product_ids: Mapped[list[str]] = mapped_column(JSONColumn, default=list)
    inventory_depth: Mapped[int] = mapped_column(Integer, default=0)
    topic_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    demand_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    demand_source: Mapped[str] = mapped_column(String(32), default="heuristic")
    requires_volatile_facts: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text)
    boost: Mapped[float] = mapped_column(Float, default=0.0)
    embedding: Mapped[list[float] | None] = mapped_column(JSONColumn)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


# -------------------------------------------------------------------- articles
class Article(Base, TimestampMixin):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_market_status", "market", "status"),
        Index("ix_articles_status_scheduled", "status", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topic_candidates.id", ondelete="SET NULL"), index=True
    )
    topic_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_query: Mapped[str] = mapped_column(Text, nullable=False)
    secondary_queries: Mapped[list[str]] = mapped_column(JSONColumn, default=list)

    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text)
    body: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    rendered_message: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    char_count: Mapped[int] = mapped_column(Integer, default=0)

    quality_scores: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    quality_score: Mapped[float | None] = mapped_column(Float)
    factuality_score: Mapped[float | None] = mapped_column(Float)
    validation_issues: Mapped[list[str]] = mapped_column(JSONColumn, default=list)

    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    generation_attempts: Mapped[int] = mapped_column(Integer, default=0)
    current_version: Mapped[int] = mapped_column(Integer, default=0)

    scheduled_for: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    published_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    approved_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    products_refreshed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)

    topic: Mapped[TopicCandidate | None] = relationship()
    versions: Mapped[list[ArticleVersion]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    claims: Mapped[list[ArticleClaim]] = relationship(
        back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )
    sources: Mapped[list[ArticleSource]] = relationship(
        back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )
    products: Mapped[list[ArticleProduct]] = relationship(
        back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )
    media: Mapped[list[ArticleMedia]] = relationship(
        back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )
    publications: Mapped[list[TelegramPublication]] = relationship(
        back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )


class ArticleVersion(Base):
    __tablename__ = "article_versions"
    __table_args__ = (UniqueConstraint("article_id", "version", name="uq_article_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONColumn, nullable=False)
    rendered_message: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    quality_scores: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_by: Mapped[str] = mapped_column(String(64), default="pipeline")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    article: Mapped[Article] = relationship(back_populates="versions")


class ArticleClaim(Base):
    __tablename__ = "article_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(48), default="general", nullable=False)
    requires_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str | None] = mapped_column(Text)
    source_tier: Mapped[int | None] = mapped_column(Integer)
    product_external_id: Mapped[str | None] = mapped_column(String(64))
    api_snapshot_id: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)
    verified_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    checked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    article: Mapped[Article] = relationship(back_populates="claims")


class ArticleSource(Base):
    __tablename__ = "article_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(Integer, default=5)
    publisher: Mapped[str | None] = mapped_column(String(255))
    accessed_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    article: Mapped[Article] = relationship(back_populates="sources")


class ArticleProduct(Base):
    __tablename__ = "article_products"
    __table_args__ = (
        UniqueConstraint("article_id", "product_external_id", name="uq_article_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    placement: Mapped[str] = mapped_column(String(32), default="compact", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)
    affiliate_url: Mapped[str | None] = mapped_column(Text)
    tracking_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    article: Mapped[Article] = relationship(back_populates="products")


class ArticleMedia(Base):
    __tablename__ = "article_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default="photo", nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="inline", nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="wegotrip_api", nullable=False)
    source_entity_type: Mapped[str | None] = mapped_column(String(32))
    source_entity_id: Mapped[str | None] = mapped_column(String(64))
    product_external_id: Mapped[str | None] = mapped_column(String(64))
    caption: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_error: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(64))
    content_length: Mapped[int | None] = mapped_column(Integer)

    article: Mapped[Article] = relationship(back_populates="media")


# ----------------------------------------------------------------- publication
class PublicationQueueItem(Base, TimestampMixin):
    __tablename__ = "publication_queue"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_publication_queue_idempotency"),
        Index("ix_publication_queue_status_time", "status", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    target: Mapped[str] = mapped_column(String(16), default="production", nullable=False)
    channel: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    scheduled_for: Mapped[dt.datetime] = mapped_column(UTCDateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    article_version: Mapped[int | None] = mapped_column(Integer)


class TelegramPublication(Base):
    __tablename__ = "telegram_publications"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_telegram_publication_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    target: Mapped[str] = mapped_column(String(16), default="production", nullable=False)
    chat_id: Mapped[str | None] = mapped_column(String(64))
    channel_username: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[int | None] = mapped_column(Integer)
    message_url: Mapped[str | None] = mapped_column(Text)
    article_version: Mapped[int | None] = mapped_column(Integer)
    telegram_response: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    published_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    edited_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    edit_count: Mapped[int] = mapped_column(Integer, default=0)

    article: Mapped[Article] = relationship(back_populates="publications")


# ------------------------------------------------------------------- analytics
class TrackingLink(Base):
    __tablename__ = "tracking_links"
    __table_args__ = (Index("ix_tracking_links_article", "article_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id", ondelete="SET NULL"))
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), default="product", nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_external_id: Mapped[str | None] = mapped_column(String(64))
    product_external_id: Mapped[str | None] = mapped_column(String(64))
    placement: Mapped[str | None] = mapped_column(String(32))
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class ClickEvent(Base):
    __tablename__ = "click_events"
    __table_args__ = (Index("ix_click_events_link_time", "tracking_link_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracking_link_id: Mapped[int] = mapped_column(
        ForeignKey("tracking_links.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[int | None] = mapped_column(Integer, index=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    visitor_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    user_agent: Mapped[str | None] = mapped_column(Text)
    referer: Mapped[str | None] = mapped_column(Text)
    is_unique: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class ConversionEvent(Base):
    """Orders / GMV imported from the affiliate back-office.

    WeGoTrip does not expose a partner conversion API in the documented Affiliate API,
    so rows are written by an importer (CSV/manual/webhook) rather than polled.
    """

    __tablename__ = "conversion_events"
    __table_args__ = (UniqueConstraint("external_order_id", name="uq_conversion_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    article_id: Mapped[int | None] = mapped_column(Integer, index=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    product_external_id: Mapped[str | None] = mapped_column(String(64))
    gmv: Mapped[float] = mapped_column(Float, default=0.0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    currency_code: Mapped[str] = mapped_column(String(8), default="EUR")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    occurred_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict)


# -------------------------------------------------------------- AI accounting
class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str | None] = mapped_column(String(8))
    task: Mapped[str] = mapped_column(String(48), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class LLMRun(Base):
    __tablename__ = "llm_runs"
    __table_args__ = (Index("ix_llm_runs_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    article_id: Mapped[int | None] = mapped_column(Integer, index=True)
    topic_id: Mapped[int | None] = mapped_column(Integer)
    market: Mapped[str | None] = mapped_column(String(8))
    task: Mapped[str] = mapped_column(String(48), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    web_search_calls: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    error: Mapped[str | None] = mapped_column(Text)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class CostLedgerEntry(Base):
    __tablename__ = "cost_ledger"
    __table_args__ = (Index("ix_cost_ledger_day_market", "spend_date", "market"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spend_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    market: Mapped[str | None] = mapped_column(String(8))
    article_id: Mapped[int | None] = mapped_column(Integer, index=True)
    llm_run_id: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), default="llm", nullable=False)
    task: Mapped[str | None] = mapped_column(String(48))
    model: Mapped[str | None] = mapped_column(String(64))
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class BudgetReservation(Base):
    """A short-lived hold placed on the daily budget before a generation job runs."""

    __tablename__ = "budget_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spend_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    article_id: Mapped[int | None] = mapped_column(Integer, index=True)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="held", nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    released_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONColumn, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class VerifiedFactCache(Base):
    """Cache of externally verified evergreen facts (spec §48.8)."""

    __tablename__ = "verified_fact_cache"
    __table_args__ = (UniqueConstraint("market", "fact_key", name="uq_verified_fact_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(48), default="general", nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="verified", nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str | None] = mapped_column(Text)
    source_tier: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    verified_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)


__all__ = [
    "Article",
    "ArticleClaim",
    "ArticleMedia",
    "ArticleProduct",
    "ArticleSource",
    "ArticleVersion",
    "Attraction",
    "BudgetReservation",
    "CatalogSnapshot",
    "Category",
    "City",
    "ClickEvent",
    "Collection",
    "ConversionEvent",
    "CostLedgerEntry",
    "Country",
    "KeywordCluster",
    "LLMRun",
    "Market",
    "Product",
    "ProductAttraction",
    "ProductCategory",
    "ProductCollection",
    "ProductMedia",
    "PromptVersion",
    "PublicationQueueItem",
    "QueryCandidate",
    "SearchDemandSnapshot",
    "SyncRun",
    "SystemSetting",
    "TelegramPublication",
    "TopicCandidate",
    "TrackingLink",
    "VerifiedFactCache",
]
