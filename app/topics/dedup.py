"""Deduplication and cannibalization protection.

Three layers, cheapest first:

1. ``topic_key`` — exact ``market × entity × intent`` identity.
2. ``canonical_query`` — "things to do in Paris", "best things to do in Paris" and
   "top things to do in Paris" all normalise to the same canonical form.
3. Vector similarity over the query + entity + title, so semantically equal topics
   phrased differently are still caught.

The vectoriser is a hashed character-n-gram model: deterministic, free and offline,
so deduplication never consumes the AI budget.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Market, Settings, get_settings
from app.db.enums import ArticleStatus, TopicStatus
from app.db.models import Article, TopicCandidate

#: Modifiers that add no new search intent — stripped when canonicalising.
_FILLER_WORDS = {
    "en": {
        "the",
        "a",
        "an",
        "of",
        "in",
        "at",
        "to",
        "for",
        "and",
        "or",
        "your",
        "you",
        "best",
        "top",
        "great",
        "greatest",
        "good",
        "must",
        "see",
        "visit",
        "guide",
        "what",
        "are",
        "is",
        "how",
        "do",
        "does",
        "can",
        "should",
        "i",
        "we",
        "ultimate",
        "complete",
        "perfect",
        "amazing",
        "awesome",
        "epic",
        "cool",
        "things",
        "thing",
        "place",
        "places",
        "list",
        "ideas",
        "tips",
    },
    "ru": {
        "в",
        "во",
        "на",
        "по",
        "к",
        "с",
        "со",
        "из",
        "для",
        "и",
        "или",
        "а",
        "но",
        "что",
        "как",
        "где",
        "куда",
        "какие",
        "какой",
        "какая",
        "самые",
        "самый",
        "лучшие",
        "лучший",
        "лучшая",
        "топ",
        "главные",
        "главное",
        "стоит",
        "нужно",
        "надо",
        "можно",
        "посмотреть",
        "увидеть",
        "сходить",
        "поехать",
        "обязательно",
        "интересного",
        "интересные",
        "места",
        "место",
        "список",
    },
}

_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)
_NGRAM_SIZE = 4
_VECTOR_DIM = 4096


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    text = text.replace("ё", "е")
    return _WORD_RE.sub(" ", text).strip()


def canonicalize_query(query: str, market: Market) -> str:
    """Reduce a query to its intent-bearing tokens, sorted for order-independence."""
    fillers = _FILLER_WORDS.get(market, set())
    tokens = [token for token in normalize_text(query).split() if token and token not in fillers]
    if not tokens:
        tokens = normalize_text(query).split()
    return " ".join(sorted(set(tokens)))


def topic_key(market: Market, entity_type: str, entity_external_id: str, intent: str) -> str:
    return f"{market}:{entity_type}:{entity_external_id}:{intent}"


def topic_slug(market: Market, entity_name: str, intent: str) -> str:
    return slugify(f"{market}-{entity_name}-{intent}")[:200]


def vectorize(text: str) -> dict[int, float]:
    """L2-normalised hashed character-n-gram vector."""
    normalized = f" {normalize_text(text)} "
    if len(normalized) <= _NGRAM_SIZE:
        grams = [normalized]
    else:
        grams = [normalized[i : i + _NGRAM_SIZE] for i in range(len(normalized) - _NGRAM_SIZE + 1)]
    counts = Counter(hash(gram) % _VECTOR_DIM for gram in grams)
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {key: value / norm for key, value in counts.items()}


def cosine_similarity(left: dict[int, float], right: dict[int, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def similarity(a: str, b: str) -> float:
    return cosine_similarity(vectorize(a), vectorize(b))


@dataclass(frozen=True, slots=True)
class DuplicateVerdict:
    is_duplicate: bool
    reason: str | None = None
    similarity: float = 0.0
    conflicting_topic_id: int | None = None
    conflicting_article_id: int | None = None

    @property
    def ok(self) -> bool:
        return not self.is_duplicate


#: Statuses that still "own" an intent and therefore block a near-duplicate.
_BLOCKING_ARTICLE_STATUSES = (
    ArticleStatus.DRAFT,
    ArticleStatus.NEEDS_REVIEW,
    ArticleStatus.APPROVED,
    ArticleStatus.SCHEDULED,
    ArticleStatus.PUBLISHING,
    ArticleStatus.PUBLISHED,
    ArticleStatus.GENERATING,
    ArticleStatus.RESEARCHING,
)

_BLOCKING_TOPIC_STATUSES = (
    TopicStatus.QUEUED,
    TopicStatus.GENERATING,
    TopicStatus.USED,
)


class DeduplicationService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def check_topic(
        self,
        market: Market,
        *,
        entity_type: str,
        entity_external_id: str,
        entity_name: str,
        intent: str,
        primary_query: str,
        exclude_topic_id: int | None = None,
    ) -> DuplicateVerdict:
        key = topic_key(market, entity_type, entity_external_id, intent)
        existing = self.session.scalar(
            select(TopicCandidate).where(
                TopicCandidate.market == market, TopicCandidate.topic_key == key
            )
        )
        if (
            existing is not None
            and existing.id != exclude_topic_id
            and existing.status in {s.value for s in _BLOCKING_TOPIC_STATUSES}
        ):
            return DuplicateVerdict(
                True, "same entity and intent already in the pipeline", 1.0, existing.id
            )

        canonical = canonicalize_query(primary_query, market)
        canonical_clash = self.session.scalar(
            select(TopicCandidate).where(
                TopicCandidate.market == market,
                TopicCandidate.canonical_query == canonical,
                TopicCandidate.entity_external_id == entity_external_id,
                TopicCandidate.status.in_([s.value for s in _BLOCKING_TOPIC_STATUSES]),
            )
        )
        if canonical_clash is not None and canonical_clash.id != exclude_topic_id:
            return DuplicateVerdict(
                True, "canonical query already covered", 1.0, canonical_clash.id
            )

        threshold = self.settings.dedup_similarity_threshold
        probe = vectorize(f"{primary_query} {entity_name}")

        articles = self.session.scalars(
            select(Article).where(
                Article.market == market,
                Article.entity_external_id == entity_external_id,
                Article.status.in_([s.value for s in _BLOCKING_ARTICLE_STATUSES]),
            )
        ).all()
        for article in articles:
            score = cosine_similarity(
                probe, vectorize(f"{article.primary_query} {article.entity_name}")
            )
            if score >= threshold:
                return DuplicateVerdict(
                    True,
                    f"semantically close to article #{article.id} ({score:.2f})",
                    score,
                    conflicting_article_id=article.id,
                )

        siblings = self.session.scalars(
            select(TopicCandidate).where(
                TopicCandidate.market == market,
                TopicCandidate.entity_external_id == entity_external_id,
                TopicCandidate.status.in_([s.value for s in _BLOCKING_TOPIC_STATUSES]),
            )
        ).all()
        for sibling in siblings:
            if sibling.id == exclude_topic_id:
                continue
            score = cosine_similarity(
                probe, vectorize(f"{sibling.primary_query} {sibling.entity_name}")
            )
            if score >= threshold:
                return DuplicateVerdict(
                    True,
                    f"semantically close to topic #{sibling.id} ({score:.2f})",
                    score,
                    conflicting_topic_id=sibling.id,
                )

        return DuplicateVerdict(False)


__all__ = [
    "DeduplicationService",
    "DuplicateVerdict",
    "canonicalize_query",
    "cosine_similarity",
    "normalize_text",
    "similarity",
    "topic_key",
    "topic_slug",
    "vectorize",
]
