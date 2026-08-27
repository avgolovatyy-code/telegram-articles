"""Claim detection, classification and the VERIFY-OR-OMIT rule.

Two independent layers guard against hallucinated facts:

1. A deterministic scanner (this module) that finds volatile statements in the produced
   text by pattern. It runs even when the model forgets to declare a claim.
2. An LLM claim extractor that catches statements the patterns miss.

Anything classified as critical must end up ``verified`` with a source, otherwise the
sentence carrying it is removed before publication. Nothing is ever "plausibly filled in".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import Market
from app.db.enums import CRITICAL_CLAIM_CATEGORIES, ClaimCategory, ClaimStatus, ClaimType
from app.generation.schemas import ArticleDocument

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

#: (category, compiled pattern) pairs. Patterns are intentionally broad: a false
#: positive costs one omitted sentence, a false negative costs a wrong published fact.
_PATTERNS: list[tuple[ClaimCategory, re.Pattern[str]]] = [
    (
        ClaimCategory.OPENING_HOURS,
        re.compile(
            r"\b(open(s|ing)?\s+(from|at|until|till)|closes?\s+at|opening hours|last entry"
            r"|часы?\s+работы|открыт[аоы]?\s+(с|до)|закрыва(ется|ются)\s+в|работает\s+с)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.CLOSING_DAYS,
        re.compile(
            r"\b(closed on|closed every|day off|выходной день|закрыт[аоы]?\s+(по|в)\s+"
            r"(понедельник|вторник|сред|четверг|пятниц|суббот|воскресень))\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.TICKET_PRICE,
        re.compile(
            r"(ticket[s]?\s+(cost|costs|price|prices|is|are)\s*[€$£₽]?\s*\d"
            r"|entry\s+(costs?|is)\s*[€$£₽]?\s*\d"
            r"|билет[а-я]*\s+(стоит|стоят|обойд[её]тся)\s*\d"
            r"|вход\s+стоит\s*\d)",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.CURRENT_EXHIBITION,
        re.compile(
            r"\b(currently on (show|display)|current exhibition|temporary exhibition|until \d{1,2}"
            r"\s+\w+\s+20\d\d|сейчас проходит|временная выставка|до \d{1,2}\s+\w+\s+20\d\d)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.TEMPORARY_RESTRICTION,
        re.compile(
            r"\b(under renovation|temporarily closed|refurbishment|scaffolding"
            r"|на реконструкции|временно закрыт|ремонтные работы)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.SKIP_THE_LINE,
        re.compile(
            r"\b(skip[- ]the[- ]line|без очереди|вход без очереди|fast track)\b", re.IGNORECASE
        ),
    ),
    (
        ClaimCategory.ENTRANCE_RULES,
        re.compile(
            r"\b(dress code|no (photos|photography|backpacks|large bags)|bag policy"
            r"|нельзя (фотографировать|с рюкзаком)|дресс-код|правила входа)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.TRANSPORT,
        re.compile(
            r"\b(metro line \w+|bus (number|no\.?) ?\d+|tram \d+|take line \d+"
            r"|станция метро|автобус №? ?\d+|трамвай №? ?\d+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.ACCESSIBILITY,
        re.compile(
            r"\b(wheelchair accessible|step[- ]free|accessible entrance"
            r"|доступн[а-я]+ для колясок|безбарьерн)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.CANCELLATION_POLICY,
        re.compile(
            r"\b(free cancellation|cancel(lation)? (up to|within) \d+"
            r"|бесплатная отмена|отменить за \d+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.SCHEDULE,
        re.compile(
            r"\b(every (day|hour) at \d{1,2}[:.]\d\d|at \d{1,2}[:.]\d\d\s*(am|pm)?\b"
            r"|расписание|в \d{1,2}[:.]\d\d\b)",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimCategory.ADDRESS,
        re.compile(
            r"\b(\d{1,4}\s+(rue|via|calle|street|st\.|avenue|ave\.|boulevard)"
            r"|улица\s+[А-ЯЁ][а-яё]+,?\s*\d|д\.\s?\d{1,4})\b",
            re.IGNORECASE,
        ),
    ),
]

#: Numbers that are almost certainly volatile when they appear next to money or counts.
_NUMERIC_RE = re.compile(
    r"[€$£₽]\s?\d|\d+\s?(euros?|dollars?|pounds?|рубл|евро|доллар)", re.IGNORECASE
)


@dataclass(slots=True)
class DetectedClaim:
    text: str
    category: ClaimCategory
    requires_verification: bool
    claim_type: ClaimType = ClaimType.VERIFIED_EXTERNAL
    product_external_id: str | None = None
    supported_by_api: bool = False

    @property
    def is_critical(self) -> bool:
        return self.requires_verification and str(self.category) in CRITICAL_CLAIM_CATEGORIES


@dataclass(slots=True)
class ClaimScanResult:
    claims: list[DetectedClaim] = field(default_factory=list)

    @property
    def critical(self) -> list[DetectedClaim]:
        return [claim for claim in self.claims if claim.is_critical]


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]


def classify_sentence(sentence: str) -> ClaimCategory | None:
    for category, pattern in _PATTERNS:
        if pattern.search(sentence):
            return category
    if _NUMERIC_RE.search(sentence):
        return ClaimCategory.NUMERIC_FACT
    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def scan_document(
    document: ArticleDocument,
    *,
    api_facts: list[str],
    market: Market = "en",
) -> ClaimScanResult:
    """Find every volatile statement in the produced text."""
    fact_blob = _normalize(" ".join(api_facts))
    result = ClaimScanResult()
    seen: set[str] = set()

    for sentence in split_sentences(document.plain_text()):
        category = classify_sentence(sentence)
        if category is None:
            continue
        key = _normalize(sentence)
        if key in seen:
            continue
        seen.add(key)
        supported = _supported_by_api(sentence, fact_blob)
        result.claims.append(
            DetectedClaim(
                text=sentence,
                category=category,
                requires_verification=not supported,
                claim_type=ClaimType.WEGOTRIP_API if supported else ClaimType.VERIFIED_EXTERNAL,
                supported_by_api=supported,
            )
        )
    return result


def _supported_by_api(sentence: str, fact_blob: str) -> bool:
    """True when every number in the sentence also appears in the API facts."""
    numbers = re.findall(r"\d+(?:[.,]\d+)?", sentence)
    if not numbers:
        return False
    return all(number in fact_blob for number in numbers)


def strip_unverified(
    document: ArticleDocument, unverified: list[str]
) -> tuple[ArticleDocument, int]:
    """Remove sentences carrying unverified critical claims (VERIFY OR OMIT).

    Returns the cleaned document and the number of removed sentences.
    """
    targets = {_normalize(text) for text in unverified if text.strip()}
    if not targets:
        return document, 0

    removed = 0

    def clean(text: str | None) -> tuple[str | None, int]:
        if not text:
            return text, 0
        sentences = split_sentences(text)
        if not sentences:
            return text, 0
        kept = [s for s in sentences if _normalize(s) not in targets]
        dropped = len(sentences) - len(kept)
        if dropped == 0:
            return text, 0
        return (" ".join(kept).strip() or None), dropped

    data = document.model_copy(deep=True)

    data.intro, dropped = clean(data.intro)
    removed += dropped
    data.intro = data.intro or ""

    for section in data.sections:
        new_blocks = []
        for block in section.blocks:
            block.text, dropped = clean(block.text)
            removed += dropped
            kept_items = [item for item in block.items if _normalize(item) not in targets]
            removed += len(block.items) - len(kept_items)
            block.items = kept_items
            if block.text or block.items or block.rows or block.type == "divider":
                new_blocks.append(block)
        section.blocks = new_blocks
    data.sections = [section for section in data.sections if section.blocks]

    kept_faq = []
    for item in data.faq:
        cleaned, dropped = clean(item.answer)
        removed += dropped
        if cleaned:
            item.answer = cleaned
            kept_faq.append(item)
    data.faq = kept_faq

    if data.closing:
        data.closing, dropped = clean(data.closing)
        removed += dropped

    return data, removed


__all__ = [
    "ClaimScanResult",
    "ClaimStatus",
    "DetectedClaim",
    "classify_sentence",
    "scan_document",
    "split_sentences",
    "strip_unverified",
]
