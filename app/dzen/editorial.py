"""Independent editorial decision: deterministic blockers plus LLM critic payload."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.dzen.genre import GENRE_INTERVIEW, contract_for
from app.dzen.products import DzenProductPick
from app.dzen.quality import run_gates
from app.dzen.schemas import DzenArticleAST, DzenCriticReport


class EditorialIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    claim_id: str | None = None
    span: str = ""
    explanation: str = ""
    proposed_fix: str = ""


class EditorialCoverage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reader_promise_met: bool = True
    days_complete: bool | None = None
    new_information_by_section: bool = True


class EditorialScores(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reader_value: float = 0.0
    originality: float = 0.0
    specificity: float = 0.0
    clarity: float = 0.0
    structure: float = 0.0
    factual_support: float = 0.0
    commercial_naturalness: float = 0.0


class EditorialDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision: Literal["accept", "revise", "needs_research", "hold"] = "revise"
    blocking_issues: list[EditorialIssue] = Field(default_factory=list)
    non_blocking_issues: list[EditorialIssue] = Field(default_factory=list)
    coverage: EditorialCoverage = Field(default_factory=EditorialCoverage)
    scores: EditorialScores = Field(default_factory=EditorialScores)
    evidence_ids: list[str] = Field(default_factory=list)
    prompt_version: str = "dzen_russian_style_v2"


def _issue(code: str, explanation: str, fix: str = "") -> EditorialIssue:
    return EditorialIssue(code=code, explanation=explanation, proposed_fix=fix or explanation)


def evaluate_editorial(
    ast: DzenArticleAST,
    *,
    products: list[DzenProductPick],
    image_urls: list[str],
    cover_url: str | None,
    first_person_evidence: bool = False,
    genre: str | None = None,
) -> EditorialDecision:
    decision = EditorialDecision()
    gates = run_gates(
        ast,
        products=products,
        image_urls=image_urls,
        cover_url=cover_url,
        first_person_evidence=first_person_evidence,
    )
    blocking: list[EditorialIssue] = []
    soft: list[EditorialIssue] = []
    for message in gates.issues:
        if "repetition" in message:
            soft.append(_issue("repetition", message, "Consolidate repeated theses"))
            continue
        if "awkward_russian" in message:
            blocking.append(
                _issue(
                    "awkward_russian",
                    message,
                    "Перепишите фразу естественным русским языком, называя конкретное действие "
                    "или наблюдение вместо абстрактной метафоры.",
                )
            )
            continue
        if "chronology_conflict" in message:
            blocking.append(_issue("chronology_conflict", message))
        elif "unsuitable_venue" in message:
            blocking.append(_issue("unsuitable_venue", message))
        elif "misleading_product" in message or "locale=" in message:
            blocking.append(_issue("misleading_product", message))
        elif "promise" in message or "day " in message or "two days" in message:
            blocking.append(_issue("headline_promise_gap", message))
        elif "audio-guide" in message or "route_infeasible" in message:
            blocking.append(_issue("route_infeasible", message))
        elif "hours" in message or "first-person" in message or "payment" in message:
            blocking.append(_issue("unsupported_claim", message))
        else:
            blocking.append(_issue("unsupported_claim", message))

    if ast.format in {"dzen_first_person_report", "dzen_interview"} and not first_person_evidence:
        blocking.append(
            _issue(
                "unsupported_claim",
                "interview/first-person without source notes",
                "Switch genre or drop invented witnesses",
            )
        )
    genre_key = genre or ast.format
    contract = contract_for(None, ast.format)
    if contract.genre == GENRE_INTERVIEW and not first_person_evidence:
        blocking.append(_issue("unsupported_claim", "no interview evidence in the dossier"))

    days_issue = any(item.code == "headline_promise_gap" for item in blocking)
    decision.blocking_issues = blocking
    decision.non_blocking_issues = soft
    decision.coverage = EditorialCoverage(
        reader_promise_met=not days_issue,
        days_complete=not days_issue,
        new_information_by_section=not soft,
    )
    if blocking:
        hard_research = any("hours" in item.explanation for item in blocking)
        decision.decision = "needs_research" if hard_research else "revise"
    elif soft:
        decision.decision = "revise"
    else:
        decision.decision = "accept"
    filled = 1.0 if decision.decision == "accept" else 0.4
    decision.scores = EditorialScores(
        reader_value=filled,
        originality=filled,
        specificity=filled,
        clarity=filled,
        structure=filled,
        factual_support=0.2 if blocking else 0.9,
        commercial_naturalness=0.8 if products else 1.0,
    )
    decision.evidence_ids = [f"genre:{genre_key}"]
    return decision


def decision_to_critic(decision: EditorialDecision) -> DzenCriticReport:
    return DzenCriticReport(
        pass_gate=decision.decision == "accept",
        quality_score=decision.scores.reader_value,
        factuality_score=decision.scores.factual_support,
        issues=[item.explanation for item in decision.blocking_issues],
        rewrite_hints=[
            item.proposed_fix or item.explanation
            for item in decision.blocking_issues + decision.non_blocking_issues
        ],
    )


def editorial_json_schema() -> dict[str, Any]:
    issue = {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "claim_id", "span", "explanation", "proposed_fix"],
        "properties": {
            "code": {"type": "string"},
            "claim_id": {"type": ["string", "null"]},
            "span": {"type": "string"},
            "explanation": {"type": "string"},
            "proposed_fix": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "decision",
            "blocking_issues",
            "non_blocking_issues",
            "coverage",
            "scores",
            "evidence_ids",
            "prompt_version",
        ],
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["accept", "revise", "needs_research", "hold"],
            },
            "blocking_issues": {"type": "array", "items": issue},
            "non_blocking_issues": {"type": "array", "items": issue},
            "coverage": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reader_promise_met", "days_complete", "new_information_by_section"],
                "properties": {
                    "reader_promise_met": {"type": "boolean"},
                    "days_complete": {"type": ["boolean", "null"]},
                    "new_information_by_section": {"type": "boolean"},
                },
            },
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reader_value",
                    "originality",
                    "specificity",
                    "clarity",
                    "structure",
                    "factual_support",
                    "commercial_naturalness",
                ],
                "properties": {key: {"type": "number"} for key in EditorialScores.model_fields},
            },
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "prompt_version": {"type": "string"},
        },
    }


MAX_REVISIONS = 2

__all__ = [
    "MAX_REVISIONS",
    "EditorialCoverage",
    "EditorialDecision",
    "EditorialIssue",
    "EditorialScores",
    "decision_to_critic",
    "editorial_json_schema",
    "evaluate_editorial",
]
