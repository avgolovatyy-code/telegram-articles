"""Structured Chief Editor payloads (spec 3.0 §6)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.editorial.mechanics import (
    AUDIENCE_AXES,
    CHANNEL_IDS,
    EDITORIAL_MECHANICS,
    default_audience_axis,
    default_channel_targets,
    default_mechanic_for_pillar,
)
from app.editorial.pillars import (
    AUDIENCE_VALUES,
    POST_FORMATS,
    accepted_format_codes,
    accepted_pillar_codes,
    canonical_format,
    canonical_pillar,
    pillar_codes,
)

EditorialAction = Literal["add", "keep", "move", "replace", "drop", "request_research", "skip"]
ProductRecommendation = Literal["none", "optional", "required"]
SourceLinkPolicy = Literal[
    "internal_sources_only", "verified_external_allowed", "no_external_links"
]
TravelPracticalityStatus = Literal[
    "not_applicable", "verification_required", "verified", "unverified", "hold"
]


class EditorialDecision(BaseModel):
    action: EditorialAction
    slot_id: int | None = None
    candidate_id: str | None = None
    planned_date: dt.date
    audience: str = "both"
    pillar: str
    format: str
    editorial_mechanic: str = "editorial_feature"
    audience_axis: str = "culture_and_curiosity"
    channel_targets: list[str] = Field(default_factory=list)
    destination_country: str | None = None
    destination_city: str | None = None
    angle: str | None = None
    reader_value: str | None = None
    hook_hypothesis: str | None = None
    fact_ids_needed: list[str] = Field(default_factory=list)
    product_recommendation: ProductRecommendation = "optional"
    source_link_policy: SourceLinkPolicy = "internal_sources_only"
    priority: int = Field(default=50, ge=0, le=100)
    why_now: str | None = None
    why_replace_existing: str | None = None
    why_worth_reading_without_purchase: str | None = None
    travel_practicality_status: TravelPracticalityStatus = "not_applicable"
    russia_demand_evidence_ids: list[str] = Field(default_factory=list)
    market_fit_reason: str | None = None
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
        if value not in accepted_pillar_codes():
            raise ValueError(f"unknown pillar {value}")
        return canonical_pillar(value)

    @field_validator("format")
    @classmethod
    def _format(cls, value: str) -> str:
        if value not in accepted_format_codes():
            raise ValueError(f"unknown format {value}")
        return canonical_format(value)

    @field_validator("editorial_mechanic")
    @classmethod
    def _mechanic(cls, value: str) -> str:
        if value not in EDITORIAL_MECHANICS:
            raise ValueError(f"unknown editorial_mechanic {value}")
        return value

    @field_validator("audience_axis")
    @classmethod
    def _axis(cls, value: str) -> str:
        if value not in AUDIENCE_AXES:
            raise ValueError(f"unknown audience_axis {value}")
        return value

    @field_validator("channel_targets")
    @classmethod
    def _channels(cls, value: list[str]) -> list[str]:
        cleaned = [item for item in value if item in CHANNEL_IDS]
        return cleaned

    def fill_defaults(self, market: str) -> EditorialDecision:
        updates: dict[str, Any] = {}
        if not self.editorial_mechanic:
            updates["editorial_mechanic"] = default_mechanic_for_pillar(self.pillar)
        if not self.audience_axis:
            updates["audience_axis"] = default_audience_axis(
                market=market, audience=self.audience, pillar=self.pillar
            )
        if not self.channel_targets:
            updates["channel_targets"] = default_channel_targets(market)
        elif market == "en":
            updates["channel_targets"] = ["telegram_en"]
        if updates:
            return self.model_copy(update=updates)
        if market == "en" and self.channel_targets != ["telegram_en"]:
            return self.model_copy(update={"channel_targets": ["telegram_en"]})
        return self


class EditorialDecisionSet(BaseModel):
    market: str
    run_date: dt.date
    editorial_thesis: str
    decisions: list[EditorialDecision] = Field(default_factory=list)
    empty_slots_justification: list[str] = Field(default_factory=list)
    daily_summary: str = ""
    risks: list[str] = Field(default_factory=list)
    rejected_topics: list[dict[str, Any]] = Field(default_factory=list)
    diversity_analysis: dict[str, Any] = Field(default_factory=dict)

    def normalized(self, market: str, run_date: dt.date) -> EditorialDecisionSet:
        decisions = [item.fill_defaults(market) for item in self.decisions]
        return self.model_copy(
            update={"market": market, "run_date": run_date, "decisions": decisions}
        )


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
        "pillar": {"type": "string", "enum": accepted_pillar_codes()},
        "format": {"type": "string", "enum": accepted_format_codes()},
        "editorial_mechanic": {"type": "string", "enum": list(EDITORIAL_MECHANICS)},
        "audience_axis": {"type": "string", "enum": list(AUDIENCE_AXES)},
        "channel_targets": {
            "type": "array",
            "items": {"type": "string", "enum": list(CHANNEL_IDS)},
        },
        "destination_country": {"type": ["string", "null"]},
        "destination_city": {"type": ["string", "null"]},
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
        "why_worth_reading_without_purchase": {"type": ["string", "null"]},
        "travel_practicality_status": {
            "type": "string",
            "enum": [
                "not_applicable",
                "verification_required",
                "verified",
                "unverified",
                "hold",
            ],
        },
        "russia_demand_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "market_fit_reason": {"type": ["string", "null"]},
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
        "editorial_mechanic",
        "audience_axis",
        "channel_targets",
        "destination_country",
        "destination_city",
        "angle",
        "reader_value",
        "hook_hypothesis",
        "fact_ids_needed",
        "product_recommendation",
        "source_link_policy",
        "priority",
        "why_now",
        "why_replace_existing",
        "why_worth_reading_without_purchase",
        "travel_practicality_status",
        "russia_demand_evidence_ids",
        "market_fit_reason",
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
            "rejected_topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": ["string", "null"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "reason"],
                },
            },
            "diversity_analysis": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "notes": {"type": "string"},
                    "mechanic_mix": {"type": "string"},
                    "geo_mix": {"type": "string"},
                },
                "required": ["notes", "mechanic_mix", "geo_mix"],
            },
        },
        "required": [
            "market",
            "run_date",
            "editorial_thesis",
            "decisions",
            "empty_slots_justification",
            "daily_summary",
            "risks",
            "rejected_topics",
            "diversity_analysis",
        ],
    }


__all__ = [
    "POST_FORMATS",
    "EditorialDecision",
    "EditorialDecisionSet",
    "editorial_decision_json_schema",
    "pillar_codes",
]
