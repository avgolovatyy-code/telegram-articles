"""String enumerations shared by the ORM models and the business logic."""

from __future__ import annotations

from enum import StrEnum


class EntityType(StrEnum):
    COUNTRY = "country"
    CITY = "city"
    ATTRACTION = "attraction"
    CATEGORY = "category"
    COLLECTION = "collection"
    PRODUCT = "product"


class TopicStatus(StrEnum):
    CANDIDATE = "candidate"
    QUEUED = "queued"
    GENERATING = "generating"
    USED = "used"
    REJECTED = "rejected"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"


class ArticleStatus(StrEnum):
    CANDIDATE = "candidate"
    RESEARCHING = "researching"
    GENERATING = "generating"
    DRAFT = "draft"
    VALIDATION_FAILED = "validation_failed"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"
    REJECTED = "rejected"


TERMINAL_ARTICLE_STATUSES = {
    ArticleStatus.PUBLISHED,
    ArticleStatus.ARCHIVED,
    ArticleStatus.REJECTED,
}


class ClaimType(StrEnum):
    """Where a factual statement came from (spec §16)."""

    WEGOTRIP_API = "wegotrip_api"
    VERIFIED_EXTERNAL = "verified_external"
    NARRATIVE = "narrative"


class ClaimStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"
    OMITTED = "omitted"


class ClaimCategory(StrEnum):
    """Volatile fact categories that always require verification."""

    OPENING_HOURS = "opening_hours"
    CLOSING_DAYS = "closing_days"
    TICKET_PRICE = "ticket_price"
    TEMPORARY_RESTRICTION = "temporary_restriction"
    ADDRESS = "address"
    AVAILABILITY = "availability"
    DURATION = "duration"
    SKIP_THE_LINE = "skip_the_line"
    ENTRANCE_RULES = "entrance_rules"
    SCHEDULE = "schedule"
    CURRENT_EXHIBITION = "current_exhibition"
    CANCELLATION_POLICY = "cancellation_policy"
    ACCESSIBILITY = "accessibility"
    TRANSPORT = "transport"
    NUMERIC_FACT = "numeric_fact"
    HISTORICAL = "historical"
    GENERAL = "general"


#: Categories that may never be published without a verified source.
CRITICAL_CLAIM_CATEGORIES: frozenset[str] = frozenset(
    {
        ClaimCategory.OPENING_HOURS,
        ClaimCategory.CLOSING_DAYS,
        ClaimCategory.TICKET_PRICE,
        ClaimCategory.TEMPORARY_RESTRICTION,
        ClaimCategory.ADDRESS,
        ClaimCategory.AVAILABILITY,
        ClaimCategory.SKIP_THE_LINE,
        ClaimCategory.ENTRANCE_RULES,
        ClaimCategory.SCHEDULE,
        ClaimCategory.CURRENT_EXHIBITION,
        ClaimCategory.CANCELLATION_POLICY,
        ClaimCategory.ACCESSIBILITY,
        ClaimCategory.TRANSPORT,
        ClaimCategory.NUMERIC_FACT,
    }
)


class PublicationTarget(StrEnum):
    TEST = "test"
    PRODUCTION = "production"


class PublicationStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaKind(StrEnum):
    PHOTO = "photo"
    AUDIO = "audio"
    VOICE = "voice"
    VIDEO = "video"


class MediaSource(StrEnum):
    WEGOTRIP_API = "wegotrip_api"
    GENERATED = "generated"


class LLMTask(StrEnum):
    TOPIC_EXPANSION = "topic_expansion"
    TOPIC_SCORING = "topic_scoring"
    DEDUPLICATION = "deduplication"
    CLASSIFICATION = "classification"
    OUTLINE = "outline"
    ARTICLE_WRITE = "article_write"
    CLAIM_EXTRACTION = "claim_extraction"
    FACT_RESEARCH = "fact_research"
    QUALITY_REVIEW = "quality_review"
    IMAGE_GENERATION = "image_generation"
    REWRITE = "rewrite"


class CostKind(StrEnum):
    LLM = "llm"
    WEB_SEARCH = "web_search"
    IMAGE = "image"


__all__ = [
    "CRITICAL_CLAIM_CATEGORIES",
    "TERMINAL_ARTICLE_STATUSES",
    "ArticleStatus",
    "ClaimCategory",
    "ClaimStatus",
    "ClaimType",
    "CostKind",
    "EntityType",
    "LLMTask",
    "MediaKind",
    "MediaSource",
    "PublicationStatus",
    "PublicationTarget",
    "TopicStatus",
]
