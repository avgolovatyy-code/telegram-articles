"""Structured Chief Editor payloads (spec §6.4a)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.editorial.pillars import AUDIENCE_VALUES, POST_FORMATS, pillar_codes

EditorialAction = Literal[
    "add", "keep", "move", "replace", "drop", "request_research", "skip"
]
ProductRecommendation = Literal["none", "optional", "required"]
SourceLinkPolicy = Literal[
    "internal_sources_only", "verified_external_allowed", "no_external_links"
]


class EditorialDecision(BaseModel):
    action: EditorialAction
    slot_id: int | None = None
    candidate_id: str | None = None
    planned_date: dt.date
    audience: str = "both"
    pillar: str
    format: str
    angle: str | None = None
    reader_value: str | None = None
    hook_hypothesis: str | None = None
    fact_ids_needed: list[str] = Field(default_factory=list)
    product_recommendation: ProductRecommendation = "optional"
    source_link_policy: SourceLinkPolicy = "internal_sources_only"
    priority: int = Field(default=50, ge=0, le=100)
    why_now: str | None = None
    why_replace_existing: str | None = None
    needs_human_review: bool = False

    @field_validator("audience")
    @classmethod
    def _audience(cls, value: str) -> str:
        if value not in AUDIENCE_VALUES:
            raise ValueError(f"audience must be one of {sorted(AUDIENCE_VALUES)}")
        return value

    @field_validator("pillar")
    @classmethod
    def _pillar(cls, value: str) -> str:
        if value not in pillar_codes():
            raise ValueError(f"unknown pillar {value}")
        return value

    @field_validator("format")
    @classmethod
    def _format(cls, value: str) -> str:
        if value not in POST_FORMATS:
            raise ValueError(f"unknown format {value}")
        return value


class EditorialDecisionSet(BaseModel):
    market: str
    run_date: dt.date
    editorial_thesis: str
    decisions: list[EditorialDecision] = Field(default_factory=list)
    empty_slots_justification: list[str] = Field(default_factory=list)
    daily_summary: str = ""
    risks: list[str] = Field(default_factory=list)


_DECISION_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "add",
                "keep",
                "move",
                "replace",
                "drop",
                "request_research",
                "skip",
            ],
        },
        "slot_id": {"type": ["integer", "null"]},
        "candidate_id": {"type": ["string", "null"]},
        "planned_date": {"type": "string"},
        "audience": {"type": "string", "enum": ["local", "traveler", "both"]},
        "pillar": {"type": "string", "enum": pillar_codes()},
        "format": {"type": "string", "enum": sorted(POST_FORMATS)},
        "angle": {"type": ["string", "null"]},
        "reader_value": {"type": ["string", "null"]},
        "hook_hypothesis": {"type": ["string", "null"]},
        "fact_ids_needed": {"type": "array", "items": {"type": "string"}},
        "product_recommendation": {
            "type": "string",
            "enum": ["none", "optional", "required"],
        },
        "source_link_policy": {
            "type": "string",
            "enum": [
                "internal_sources_only",
                "verified_external_allowed",
                "no_external_links",
            ],
        },
        "priority": {"type": "integer", "minimum": 0, "maximum": 100},
        "why_now": {"type": ["string", "null"]},
        "why_replace_existing": {"type": ["string", "null"]},
        "needs_human_review": {"type": "boolean"},
    },
    "required": [
        "action",
        "slot_id",
        "candidate_id",
        "planned_date",
        "audience",
        "pillar",
        "format",
        "angle",
        "reader_value",
        "hook_hypothesis",
        "fact_ids_needed",
        "product_recommendation",
        "source_link_policy",
        "priority",
        "why_now",
        "why_replace_existing",
        "needs_human_review",
    ],
}


def editorial_decision_json_schema() -> dict[str, Any]:
    """OpenAI Responses ``strict`` JSON schema (no ``$ref`` / ``$defs``)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "market": {"type": "string", "enum": ["en", "ru"]},
            "run_date": {"type": "string"},
            "editorial_thesis": {"type": "string"},
            "decisions": {"type": "array", "items": _DECISION_ITEM},
            "empty_slots_justification": {"type": "array", "items": {"type": "string"}},
            "daily_summary": {"type": "string"},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "market",
            "run_date",
            "editorial_thesis",
            "decisions",
            "empty_slots_justification",
            "daily_summary",
            "risks",
        ],
    }


__all__ = [
    "EditorialDecision",
    "EditorialDecisionSet",
    "editorial_decision_json_schema",
]
