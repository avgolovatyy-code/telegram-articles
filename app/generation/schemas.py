"""Article JSON — the internal source of truth.

The writer model returns *this* structure, never Telegram markup. A separate renderer
turns it into an ``InputRichMessage``. Media, affiliate URLs and product facts are
supplied by code; the model may only reference them by id.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BlockType = Literal["paragraph", "list", "ordered_list", "quote", "table", "tip", "divider"]
PlacementKind = Literal["hero", "compact", "collection"]


class ArticleBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: BlockType = "paragraph"
    text: str | None = None
    items: list[str] = Field(default_factory=list)
    #: Table rows including the header row.
    rows: list[list[str]] = Field(default_factory=list)
    credit: str | None = None


class ArticleSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading: str
    level: int = 2
    blocks: list[ArticleBlock] = Field(default_factory=list)


class ProductPlacement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: str
    placement: PlacementKind = "compact"
    #: Index into ``sections``; the card is rendered after that section.
    after_section: int = 0
    pitch: str | None = None


class MediaPlacement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media_id: str
    after_section: int = 0
    caption: str | None = None


class AudioPlacement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: str
    after_section: int = 0
    caption: str | None = None


class FAQItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    answer: str


class DraftClaim(BaseModel):
    """A checkable statement extracted by (or declared by) the model."""

    model_config = ConfigDict(extra="ignore")

    claim: str
    category: str = "general"
    requires_verification: bool = False
    product_id: str | None = None


class ArticleDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    intro: str
    sections: list[ArticleSection] = Field(default_factory=list)
    product_placements: list[ProductPlacement] = Field(default_factory=list)
    media_placements: list[MediaPlacement] = Field(default_factory=list)
    audio_placements: list[AudioPlacement] = Field(default_factory=list)
    faq: list[FAQItem] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    claims: list[DraftClaim] = Field(default_factory=list)
    closing: str | None = None

    def plain_text(self) -> str:
        parts: list[str] = [self.title, self.intro]
        for section in self.sections:
            parts.append(section.heading)
            for block in section.blocks:
                if block.text:
                    parts.append(block.text)
                parts.extend(block.items)
                for row in block.rows:
                    parts.append(" ".join(row))
        for item in self.faq:
            parts.extend([item.question, item.answer])
        if self.closing:
            parts.append(self.closing)
        return "\n\n".join(part for part in parts if part)

    def char_count(self) -> int:
        return len(self.plain_text())


class QualityReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    usefulness: float = 0.0
    factuality: float = 0.0
    readability: float = 0.0
    search_intent_match: float = 0.0
    natural_language: float = 0.0
    product_relevance: float = 0.0
    spam_risk: float = 1.0
    issues: list[str] = Field(default_factory=list)

    @property
    def overall(self) -> float:
        """Mean of the positive dimensions, damped by spam risk."""
        positives = [
            self.usefulness,
            self.factuality,
            self.readability,
            self.search_intent_match,
            self.natural_language,
            self.product_relevance,
        ]
        return round(sum(positives) / len(positives) * (1.0 - min(self.spam_risk, 1.0) * 0.5), 4)


# --------------------------------------------------------------- JSON schemas
def _strict(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


ARTICLE_JSON_SCHEMA: dict[str, Any] = _strict(
    {
        "title": {"type": "string"},
        "intro": {"type": "string"},
        "sections": {
            "type": "array",
            "items": _strict(
                {
                    "heading": {"type": "string"},
                    "level": {"type": "integer"},
                    "blocks": {
                        "type": "array",
                        "items": _strict(
                            {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "paragraph",
                                        "list",
                                        "ordered_list",
                                        "quote",
                                        "table",
                                        "tip",
                                        "divider",
                                    ],
                                },
                                "text": {"type": ["string", "null"]},
                                "items": {"type": "array", "items": {"type": "string"}},
                                "rows": {
                                    "type": "array",
                                    "items": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                            ["type", "text", "items", "rows"],
                        ),
                    },
                },
                ["heading", "level", "blocks"],
            ),
        },
        "product_placements": {
            "type": "array",
            "items": _strict(
                {
                    "product_id": {"type": "string"},
                    "placement": {"type": "string", "enum": ["hero", "compact", "collection"]},
                    "after_section": {"type": "integer"},
                    "pitch": {"type": ["string", "null"]},
                },
                ["product_id", "placement", "after_section", "pitch"],
            ),
        },
        "media_placements": {
            "type": "array",
            "items": _strict(
                {
                    "media_id": {"type": "string"},
                    "after_section": {"type": "integer"},
                    "caption": {"type": ["string", "null"]},
                },
                ["media_id", "after_section", "caption"],
            ),
        },
        "audio_placements": {
            "type": "array",
            "items": _strict(
                {
                    "product_id": {"type": "string"},
                    "after_section": {"type": "integer"},
                    "caption": {"type": ["string", "null"]},
                },
                ["product_id", "after_section", "caption"],
            ),
        },
        "faq": {
            "type": "array",
            "items": _strict(
                {"question": {"type": "string"}, "answer": {"type": "string"}},
                ["question", "answer"],
            ),
        },
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": _strict(
                {
                    "claim": {"type": "string"},
                    "category": {"type": "string"},
                    "requires_verification": {"type": "boolean"},
                    "product_id": {"type": ["string", "null"]},
                },
                ["claim", "category", "requires_verification", "product_id"],
            ),
        },
        "closing": {"type": ["string", "null"]},
    },
    [
        "title",
        "intro",
        "sections",
        "product_placements",
        "media_placements",
        "audio_placements",
        "faq",
        "hashtags",
        "claims",
        "closing",
    ],
)


QUALITY_REVIEW_JSON_SCHEMA: dict[str, Any] = _strict(
    {
        "usefulness": {"type": "number"},
        "factuality": {"type": "number"},
        "readability": {"type": "number"},
        "search_intent_match": {"type": "number"},
        "natural_language": {"type": "number"},
        "product_relevance": {"type": "number"},
        "spam_risk": {"type": "number"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    [
        "usefulness",
        "factuality",
        "readability",
        "search_intent_match",
        "natural_language",
        "product_relevance",
        "spam_risk",
        "issues",
    ],
)


CLAIM_EXTRACTION_JSON_SCHEMA: dict[str, Any] = _strict(
    {
        "claims": {
            "type": "array",
            "items": _strict(
                {
                    "claim": {"type": "string"},
                    "category": {"type": "string"},
                    "requires_verification": {"type": "boolean"},
                    "product_id": {"type": ["string", "null"]},
                },
                ["claim", "category", "requires_verification", "product_id"],
            ),
        }
    },
    ["claims"],
)


FACT_VERIFICATION_JSON_SCHEMA: dict[str, Any] = _strict(
    {
        "results": {
            "type": "array",
            "items": _strict(
                {
                    "claim": {"type": "string"},
                    "status": {"type": "string", "enum": ["verified", "refuted", "unverified"]},
                    "corrected_statement": {"type": ["string", "null"]},
                    "source_url": {"type": ["string", "null"]},
                    "source_title": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                [
                    "claim",
                    "status",
                    "corrected_statement",
                    "source_url",
                    "source_title",
                    "confidence",
                ],
            ),
        }
    },
    ["results"],
)


__all__ = [
    "ARTICLE_JSON_SCHEMA",
    "CLAIM_EXTRACTION_JSON_SCHEMA",
    "FACT_VERIFICATION_JSON_SCHEMA",
    "QUALITY_REVIEW_JSON_SCHEMA",
    "ArticleBlock",
    "ArticleDocument",
    "ArticleSection",
    "AudioPlacement",
    "DraftClaim",
    "FAQItem",
    "MediaPlacement",
    "ProductPlacement",
    "QualityReview",
]
