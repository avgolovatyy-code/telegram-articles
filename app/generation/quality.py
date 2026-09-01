"""Deterministic quality gate (spec §32).

Runs before publication and independently of the LLM critic. Technical, content,
factual and search checks; a hard failure blocks publication outright.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from app.config import Market, Settings, get_settings
from app.db.enums import ClaimStatus
from app.generation.claims import split_sentences
from app.generation.context import WriterContext
from app.generation.schemas import ArticleDocument, QualityReview
from app.links.affiliate import AffiliateLinkBuilder
from app.topics.dedup import normalize_text

#: Boilerplate the style rules forbid outright.
BANNED_PHRASES = {
    "en": [
        "immerse yourself in",
        "unforgettable journey",
        "embark on an exciting adventure",
        "whether you're a seasoned traveler",
        "whether you are a seasoned traveler",
        "from iconic landmarks to hidden gems",
        "a gem that will leave no one indifferent",
        "nestled in the heart of",
        "look no further",
        "don't miss this opportunity",
        "book now",
        "must-have audio guide",
        "perfect audio companion",
        "getyourguide",
        "viator",
        "tiqets",
    ],
    "ru": [
        "погрузитесь в удивительный мир",
        "незабываемое путешествие",
        "отправьтесь в захватывающее приключение",
        "жемчужина, которая никого не оставит равнодушным",
        "не оставит равнодушным",
        "поистине уникальн",
        "маст-хэв для каждого туриста",
        "бронируйте сейчас",
        "не упустите возможность",
        "обязательный аудиогид",
        "идеальный аудиокомпаньон",
        "getyourguide",
        "viator",
        "tiqets",
    ],
}

MAX_KEYWORD_DENSITY = 0.035
MAX_REPEATED_PARAGRAPH_RATIO = 0.12


@dataclass(slots=True)
class GateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: GateResult) -> GateResult:
        return GateResult(
            passed=self.passed and other.passed,
            errors=[*self.errors, *other.errors],
            warnings=[*self.warnings, *other.warnings],
        )


class QualityGate:
    def __init__(
        self, settings: Settings | None = None, link_builder: AffiliateLinkBuilder | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.links = link_builder or AffiliateLinkBuilder(self.settings)

    def evaluate(
        self,
        document: ArticleDocument,
        context: WriterContext,
        *,
        review: QualityReview | None = None,
        claim_statuses: list[tuple[str, ClaimStatus, bool]] | None = None,
        rendered_urls: list[str] | None = None,
    ) -> GateResult:
        result = self.technical(document, context, rendered_urls or [])
        result = result.merge(self.content(document, context))
        result = result.merge(self.factual(claim_statuses or []))
        result = result.merge(self.search(document, context))
        if review is not None:
            result = result.merge(self.review_thresholds(review))
        return result

    # ------------------------------------------------------------- technical
    def technical(
        self, document: ArticleDocument, context: WriterContext, rendered_urls: list[str]
    ) -> GateResult:
        errors: list[str] = []
        warnings: list[str] = []

        chars = document.char_count()
        if chars < self.settings.article_min_chars:
            errors.append(f"article too short: {chars} < {self.settings.article_min_chars} chars")
        if chars > self.settings.article_max_chars:
            errors.append(f"article too long: {chars} > {self.settings.article_max_chars} chars")
        if chars > self.settings.telegram_rich_message_char_limit:
            errors.append("article exceeds the Telegram rich message character limit")

        if not document.title.strip():
            errors.append("empty title")
        if not document.sections:
            errors.append("article has no sections")

        allowed_products = {item.product.external_id for item in context.products}
        for placement in document.product_placements:
            if placement.product_id not in allowed_products:
                errors.append(f"product {placement.product_id} is not in the selected set")

        allowed_media = {item.id for item in context.media}
        for media_placement in document.media_placements:
            if media_placement.media_id not in allowed_media:
                errors.append(f"media {media_placement.media_id} is not an allowed WeGoTrip asset")

        for url in rendered_urls:
            if not self.links.is_store_url(url):
                continue
            if not self.links.has_affiliate_marker(url):
                errors.append(f"affiliate marker missing on {url}")

        if self.settings.enable_hashtags:
            if len(document.hashtags) > self.settings.max_hashtags:
                errors.append(
                    f"too many hashtags: {len(document.hashtags)} > {self.settings.max_hashtags}"
                )
        elif document.hashtags:
            warnings.append("hashtags disabled by configuration; they will be dropped")

        return GateResult(passed=not errors, errors=errors, warnings=warnings)

    # --------------------------------------------------------------- content
    def content(self, document: ArticleDocument, context: WriterContext) -> GateResult:
        errors: list[str] = []
        warnings: list[str] = []
        market: Market = context.market
        text = document.plain_text()
        lowered = text.lower()

        for phrase in BANNED_PHRASES.get(market, []):
            if phrase in lowered:
                errors.append(f"banned AI boilerplate: “{phrase}”")

        paragraphs = [normalize_text(p) for p in split_sentences(text) if len(p) > 60]
        if paragraphs:
            counts = Counter(paragraphs)
            repeated = sum(count - 1 for count in counts.values() if count > 1)
            if repeated / len(paragraphs) > MAX_REPEATED_PARAGRAPH_RATIO:
                errors.append("too many repeated sentences")

        if len(document.sections) < 3:
            errors.append(f"only {len(document.sections)} sections; at least 3 required")
        if len(document.sections) > 8:
            warnings.append(f"{len(document.sections)} sections is above the recommended maximum")

        product_ratio = len(document.product_placements) / max(len(document.sections), 1)
        if len(document.product_placements) > 3:
            errors.append("more than 3 product cards; keep recommendations measured")
        if product_ratio > 0.6:
            errors.append(
                "product cards are too dense relative to sections; reads as a shop window"
            )

        # Require concrete catalogue places so the piece cannot be pure philosophy.
        attraction_names = [
            str(item.get("name") or "").strip()
            for item in (context.catalog_attractions or [])
            if item.get("name")
        ]
        if len(attraction_names) >= 4:
            body_norm = normalize_text(text)
            mentioned = 0
            for name in attraction_names:
                tokens = [t for t in normalize_text(name).split() if len(t) > 3]
                # Match on a distinctive token (Sagrada, Picasso, Montjuic, …).
                if tokens and any(token in body_norm for token in tokens[:2]):
                    mentioned += 1
            required = min(4, max(3, len(attraction_names) // 3))
            if mentioned < required:
                errors.append(
                    f"too few concrete catalogue attractions named "
                    f"({mentioned} < {required}); article is too abstract"
                )

        if not document.intro.strip():
            errors.append("empty intro")

        return GateResult(passed=not errors, errors=errors, warnings=warnings)

    # --------------------------------------------------------------- factual
    def factual(self, claim_statuses: list[tuple[str, ClaimStatus, bool]]) -> GateResult:
        errors: list[str] = []
        for claim, status, critical in claim_statuses:
            if critical and status != ClaimStatus.VERIFIED:
                errors.append(f"unverified critical claim still present: “{claim[:120]}”")
        return GateResult(passed=not errors, errors=errors)

    # ---------------------------------------------------------------- search
    def search(self, document: ArticleDocument, context: WriterContext) -> GateResult:
        errors: list[str] = []
        warnings: list[str] = []
        entity = context.topic.entity_name.split("—")[0].strip()
        query_tokens = [
            t for t in normalize_text(context.topic.primary_query).split() if len(t) > 2
        ]

        title_norm = normalize_text(document.title)
        if query_tokens:
            covered = sum(1 for token in query_tokens if token in title_norm)
            if covered / len(query_tokens) < 0.5:
                errors.append("title does not reflect the primary query")

        head = normalize_text(f"{document.title} {document.intro}")[:600]
        entity_tokens = [t for t in normalize_text(entity).split() if len(t) > 2]
        if entity_tokens and not any(token[:5] in head for token in entity_tokens):
            errors.append("entity name is missing from the first screen")

        headings = " ".join(normalize_text(section.heading) for section in document.sections)
        if query_tokens and not any(token in headings for token in query_tokens):
            warnings.append("no heading picks up the primary query")

        body = normalize_text(document.plain_text())
        words = body.split()
        entity_phrase = normalize_text(entity)
        if words and entity_phrase:
            # Density of the whole entity phrase, not of its individual tokens: words
            # like "museum" or "de" are ordinary vocabulary, not stuffing.
            occurrences = body.count(entity_phrase)
            density = occurrences * max(len(entity_phrase.split()), 1) / len(words)
            if density > MAX_KEYWORD_DENSITY:
                errors.append(
                    f"keyword stuffing: “{entity}” appears {occurrences} times in "
                    f"{len(words)} words ({density:.1%})"
                )

        if any(len(section.heading.strip()) < 3 for section in document.sections):
            errors.append("a section heading is empty or meaningless")

        return GateResult(passed=not errors, errors=errors, warnings=warnings)

    # -------------------------------------------------------------- LLM gate
    def review_thresholds(self, review: QualityReview) -> GateResult:
        errors: list[str] = []
        if review.factuality < self.settings.min_factuality_score:
            errors.append(
                f"factuality {review.factuality:.2f} < {self.settings.min_factuality_score:.2f}"
            )
        if review.overall < self.settings.min_quality_score:
            errors.append(f"quality {review.overall:.2f} < {self.settings.min_quality_score:.2f}")
        return GateResult(passed=not errors, errors=errors, warnings=list(review.issues))


_HASHTAG_RE = re.compile(r"^#[0-9A-Za-zА-Яа-яЁё_]{2,40}$")


def normalize_hashtags(tags: list[str], settings: Settings) -> list[str]:
    """Hashtag Strategy: a handful of navigational tags, never a wall (spec §22)."""
    if not settings.enable_hashtags:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        candidate = tag.strip()
        if not candidate:
            continue
        if not candidate.startswith("#"):
            candidate = "#" + candidate
        candidate = candidate.replace(" ", "")
        if not _HASHTAG_RE.match(candidate):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)
        if len(cleaned) >= settings.max_hashtags:
            break
    return cleaned


__all__ = [
    "BANNED_PHRASES",
    "MAX_KEYWORD_DENSITY",
    "GateResult",
    "QualityGate",
    "normalize_hashtags",
]
