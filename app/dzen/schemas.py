"""Dzen article AST and OpenAI structured-output schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import DzenAudience, DzenFormat, DzenPillar

BlockType = Literal[
    "paragraph",
    "heading",
    "list",
    "ordered_list",
    "image",
    "product_mention",
    "takeaway",
]


class DzenClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim: str
    category: str = "general"
    source_url: str | None = None
    source_date: str | None = None
    verification_status: Literal["verified", "unverified", "disputed", "expired"] = "unverified"
    risk: Literal["low", "medium", "high"] = "low"
    article_span: str | None = None
    editor_note: str = ""


class DzenBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: BlockType = "paragraph"
    text: str | None = None
    level: int = 2
    items: list[str] = Field(default_factory=list)
    media_asset_id: str | None = None
    caption: str | None = None
    product_id: str | None = None
    after_heading: str | None = None


class DzenArticleAST(BaseModel):
    model_config = ConfigDict(extra="ignore")

    headline: str
    lead: str
    format: str
    pillar: str
    audience: str
    destination_country: str | None = None
    destination_city: str | None = None
    blocks: list[DzenBlock] = Field(default_factory=list)
    cover_media_asset_id: str | None = None
    product_ids: list[str] = Field(default_factory=list)
    practical_takeaway: str = ""
    claims: list[DzenClaim] = Field(default_factory=list)
    reader_value: str = ""
    originality_angle: str = ""

    @field_validator("headline", "lead", "practical_takeaway")
    @classmethod
    def _strip(cls, value: str) -> str:
        return (value or "").strip()


class DzenBrief(BaseModel):
    model_config = ConfigDict(extra="ignore")

    planned_date: str
    format: str = DzenFormat.CITY_GUIDE.value
    pillar: str = DzenPillar.CITY_GUIDES.value
    audience: str = DzenAudience.RUSSIAN_SPEAKING_GLOBAL.value
    destination_country: str | None = None
    destination_city: str | None = None
    angle: str
    reader_value: str
    reader_promise: str = ""
    genre: str = ""
    why_now: str = ""
    supporting_queries: list[str] = Field(default_factory=list)
    product_recommendation: Literal["none", "optional"] = "optional"
    factual_risk: Literal["low", "medium", "high"] = "low"
    intent: str = ""


class DzenDecisionSet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_date: str
    editorial_thesis: str = ""
    briefs: list[DzenBrief] = Field(default_factory=list)
    empty_slots_justification: str = ""


class DzenCriticReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pass_gate: bool = False
    quality_score: float = 0.0
    factuality_score: float = 0.0
    issues: list[str] = Field(default_factory=list)
    rewrite_hints: list[str] = Field(default_factory=list)


def _str() -> dict[str, Any]:
    return {"type": "string"}


def _str_null() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _block_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "type",
            "text",
            "level",
            "items",
            "media_asset_id",
            "caption",
            "product_id",
            "after_heading",
        ],
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "paragraph",
                    "heading",
                    "list",
                    "ordered_list",
                    "image",
                    "product_mention",
                    "takeaway",
                ],
            },
            "text": _str_null(),
            "level": {"type": "integer"},
            "items": {"type": "array", "items": _str()},
            "media_asset_id": _str_null(),
            "caption": _str_null(),
            "product_id": _str_null(),
            "after_heading": _str_null(),
        },
    }


def dzen_article_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "headline",
            "lead",
            "format",
            "pillar",
            "audience",
            "destination_country",
            "destination_city",
            "blocks",
            "cover_media_asset_id",
            "product_ids",
            "practical_takeaway",
            "claims",
            "reader_value",
            "originality_angle",
        ],
        "properties": {
            "headline": _str(),
            "lead": _str(),
            "format": {"type": "string", "enum": [item.value for item in DzenFormat]},
            "pillar": {"type": "string", "enum": [item.value for item in DzenPillar]},
            "audience": {"type": "string", "enum": [item.value for item in DzenAudience]},
            "destination_country": _str_null(),
            "destination_city": _str_null(),
            "blocks": {"type": "array", "items": _block_schema()},
            "cover_media_asset_id": _str_null(),
            "product_ids": {"type": "array", "items": _str()},
            "practical_takeaway": _str(),
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "claim",
                        "category",
                        "source_url",
                        "source_date",
                        "verification_status",
                        "risk",
                        "article_span",
                        "editor_note",
                    ],
                    "properties": {
                        "claim": _str(),
                        "category": _str(),
                        "source_url": _str_null(),
                        "source_date": _str_null(),
                        "verification_status": {
                            "type": "string",
                            "enum": ["verified", "unverified", "disputed", "expired"],
                        },
                        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                        "article_span": _str_null(),
                        "editor_note": _str(),
                    },
                },
            },
            "reader_value": _str(),
            "originality_angle": _str(),
        },
    }


def dzen_decision_json_schema() -> dict[str, Any]:
    brief = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "planned_date",
            "format",
            "pillar",
            "audience",
            "destination_country",
            "destination_city",
            "angle",
            "reader_value",
            "reader_promise",
            "genre",
            "why_now",
            "supporting_queries",
            "product_recommendation",
            "factual_risk",
            "intent",
        ],
        "properties": {
            "planned_date": _str(),
            "format": {"type": "string", "enum": [item.value for item in DzenFormat]},
            "pillar": {"type": "string", "enum": [item.value for item in DzenPillar]},
            "audience": {"type": "string", "enum": [item.value for item in DzenAudience]},
            "destination_country": _str_null(),
            "destination_city": _str_null(),
            "angle": _str(),
            "reader_value": _str(),
            "reader_promise": _str(),
            "genre": _str(),
            "why_now": _str(),
            "supporting_queries": {"type": "array", "items": _str()},
            "product_recommendation": {"type": "string", "enum": ["none", "optional"]},
            "factual_risk": {"type": "string", "enum": ["low", "medium", "high"]},
            "intent": _str(),
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["run_date", "editorial_thesis", "briefs", "empty_slots_justification"],
        "properties": {
            "run_date": _str(),
            "editorial_thesis": _str(),
            "briefs": {"type": "array", "items": brief},
            "empty_slots_justification": _str(),
        },
    }


def dzen_critic_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "pass_gate",
            "quality_score",
            "factuality_score",
            "issues",
            "rewrite_hints",
        ],
        "properties": {
            "pass_gate": {"type": "boolean"},
            "quality_score": {"type": "number"},
            "factuality_score": {"type": "number"},
            "issues": {"type": "array", "items": _str()},
            "rewrite_hints": {"type": "array", "items": _str()},
        },
    }


def dzen_claims_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["claims"],
        "properties": {
            "claims": dzen_article_json_schema()["properties"]["claims"],
        },
    }


__all__ = [
    "DzenArticleAST",
    "DzenBlock",
    "DzenBrief",
    "DzenClaim",
    "DzenCriticReport",
    "DzenDecisionSet",
    "dzen_article_json_schema",
    "dzen_claims_json_schema",
    "dzen_critic_json_schema",
    "dzen_decision_json_schema",
]
