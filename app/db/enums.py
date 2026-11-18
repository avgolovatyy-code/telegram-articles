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
    CHIEF_EDITOR = "chief_editor"
    DZEN_CHIEF_EDITOR = "dzen_chief_editor"
    DZEN_OUTLINE = "dzen_outline"
    DZEN_WRITE = "dzen_write"
    DZEN_CRITIC = "dzen_critic"
    DZEN_CLAIMS = "dzen_claims"


class CostKind(StrEnum):
    LLM = "llm"
    WEB_SEARCH = "web_search"
    IMAGE = "image"


class DzenArticleStatus(StrEnum):
    TOPIC_CANDIDATE = "topic_candidate"
    RESEARCHED = "researched"
    DRAFT = "draft"
    AI_VERIFIED = "ai_verified"
    READY_FOR_HANDOFF = "ready_for_handoff"
    HANDED_OFF = "handed_off"
    PUBLISHED_SUBMITTED = "published_submitted"
    PUBLISHED_CONFIRMED = "published_confirmed"
    NEEDS_REVISION = "needs_revision"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class DzenFormat(StrEnum):
    CITY_GUIDE = "dzen_city_guide"
    WEEKEND_ITINERARY = "dzen_weekend_itinerary"
    ATTRACTION_GUIDE = "dzen_attraction_guide"
    MUSEUM_EXHIBITION = "dzen_museum_exhibition"
    TRAVEL_HACK = "dzen_travel_hack"
    FACT_STORY = "dzen_fact_story"
    FIRST_PERSON_REPORT = "dzen_first_person_report"
    INTERVIEW = "dzen_interview"
    COMPARISON = "dzen_comparison"
    CULTURAL_FEATURE = "dzen_cultural_feature"
    PRODUCT_EXPLAINER = "dzen_product_explainer"


class DzenPillar(StrEnum):
    CITY_GUIDES = "city_guides"
    MUSEUMS = "museums"
    TRAVEL_HACKS = "travel_hacks"
    TRAVEL_STORIES = "travel_stories"
    WEEKEND_EVENTS = "weekend_events"
    PERSONAL_EXPERIENCES = "personal_experiences"
    LISTS_OPINIONS = "lists_opinions"


class DzenAudience(StrEnum):
    RUSSIA_ORIGIN_TRAVELER = "russia_origin_traveler"
    RUSSIAN_SPEAKING_GLOBAL = "russian_speaking_global"
    LOCAL_URBAN_EXPLORER = "local_urban_explorer"
    CULTURE_CURIOUS_READER = "culture_curious_reader"


FIRST_PERSON_DZEN_FORMATS = {
    DzenFormat.FIRST_PERSON_REPORT,
    DzenFormat.INTERVIEW,
}


__all__ = [
    "CRITICAL_CLAIM_CATEGORIES",
    "FIRST_PERSON_DZEN_FORMATS",
    "TERMINAL_ARTICLE_STATUSES",
    "ArticleStatus",
    "ClaimCategory",
    "ClaimStatus",
    "ClaimType",
    "CostKind",
    "DzenArticleStatus",
    "DzenAudience",
    "DzenFormat",
    "DzenPillar",
    "EntityType",
    "LLMTask",
    "MediaKind",
    "MediaSource",
    "PublicationStatus",
    "PublicationTarget",
    "TopicStatus",
]
