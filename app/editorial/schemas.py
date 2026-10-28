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


def editorial_decision_json_schema() -> dict[str, Any]:
    return EditorialDecisionSet.model_json_schema()


__all__ = [
    "EditorialDecision",
    "EditorialDecisionSet",
    "editorial_decision_json_schema",
]
