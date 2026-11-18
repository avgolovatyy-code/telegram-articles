"""Research dossier built from the brief and catalogue before the writer runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.dzen.genre import contract_for, genre_from_format
from app.dzen.products import DzenProductPick
from app.dzen.schemas import DzenArticleAST


class DossierFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_id: str
    claim: str
    source_urls: list[str] = Field(default_factory=list)
    source_type: Literal["official", "primary", "established_secondary", "catalog"] = "catalog"
    checked_at: str | None = None
    status: Literal["verified", "contested", "insufficient"] = "insufficient"
    notes: str = ""


class ArticleResearchDossier(BaseModel):
    model_config = ConfigDict(extra="ignore")

    article_id: str = ""
    content_locale: str = "ru-RU"
    audience_market: str = "RU"
    genre: str = "city_guide"
    reader_promise: str = ""
    thesis_and_angle: str = ""
    reader_takeaways: list[str] = Field(default_factory=list)
    geography: list[dict[str, str]] = Field(default_factory=list)
    freshness_class: Literal["evergreen", "seasonal", "time_sensitive"] = "evergreen"
    source_cutoff_at: str | None = None
    facts: list[DossierFact] = Field(default_factory=list)
    itinerary_blocks: list[dict[str, Any]] = Field(default_factory=list)
    product_candidates: list[dict[str, Any]] = Field(default_factory=list)
    media_candidates: list[dict[str, Any]] = Field(default_factory=list)
    unknowns_and_risks: list[str] = Field(default_factory=list)
    editorial_constraints: list[str] = Field(default_factory=list)
    product_data_discrepancies: list[str] = Field(default_factory=list)


def catalog_dossier(
    *,
    article_id: str,
    headline: str | None,
    city: str | None,
    country: str | None,
    fmt: str | None,
    brief: dict[str, Any] | None,
    products: list[DzenProductPick],
) -> ArticleResearchDossier:
    brief = brief or {}
    genre = brief.get("genre") or genre_from_format(fmt)
    contract = contract_for(genre, fmt)
    promise = (
        brief.get("reader_promise")
        or brief.get("reader_value")
        or headline
        or contract.must_contain
    )
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    facts: list[DossierFact] = []
    discrepancies: list[str] = []
    for product in products:
        facts.append(
            DossierFact(
                claim_id=f"product-{product.external_id}",
                claim=product.reader_pitch or product.title,
                source_urls=[product.affiliate_url] if product.affiliate_url else [],
                source_type="catalog",
                checked_at=now,
                status="verified",
                notes="catalogue snapshot; FAQ and how-it-works may disagree",
            )
        )
        if getattr(product, "playback_discrepancy", False):
            discrepancies.append(
                f"product {product.external_id}: FAQ says app-only, how-it-works mentions a browser"
            )
    risks = [
        "Do not invent opening hours, visa rules or card payment unless a fact is verified.",
        "Do not write first-person travel unless the brief contains real notes.",
        contract.reject_if,
    ]
    if discrepancies:
        risks.append("Playback channel is disputed — do not state it categorically.")
    return ArticleResearchDossier(
        article_id=article_id,
        genre=genre,
        reader_promise=str(promise),
        thesis_and_angle=str(brief.get("angle") or headline or ""),
        reader_takeaways=[str(brief.get("reader_value") or "")],
        geography=[{"country": country or "", "city": city or "", "location": ""}],
        source_cutoff_at=now,
        facts=facts,
        product_candidates=[
            {
                "id": product.external_id,
                "title": product.title,
                "is_free": product.is_free,
                "duration": product.duration_label,
                "distance": product.distance_label,
                "listen_in_browser": product.listen_in_browser,
                "playback_discrepancy": getattr(product, "playback_discrepancy", False),
            }
            for product in products
        ],
        unknowns_and_risks=[item for item in risks if item],
        editorial_constraints=[contract.writer_brief, contract.must_contain],
        product_data_discrepancies=discrepancies,
    )


def dossier_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "article_id",
            "genre",
            "reader_promise",
            "thesis_and_angle",
            "facts",
            "unknowns_and_risks",
        ],
        "properties": {
            "article_id": {"type": "string"},
            "content_locale": {"type": "string"},
            "audience_market": {"type": "string"},
            "genre": {"type": "string"},
            "reader_promise": {"type": "string"},
            "thesis_and_angle": {"type": "string"},
            "reader_takeaways": {"type": "array", "items": {"type": "string"}},
            "geography": {"type": "array", "items": {"type": "object"}},
            "freshness_class": {
                "type": "string",
                "enum": ["evergreen", "seasonal", "time_sensitive"],
            },
            "source_cutoff_at": {"type": ["string", "null"]},
            "facts": {"type": "array"},
            "itinerary_blocks": {"type": "array"},
            "product_candidates": {"type": "array"},
            "media_candidates": {"type": "array"},
            "unknowns_and_risks": {"type": "array", "items": {"type": "string"}},
            "editorial_constraints": {"type": "array", "items": {"type": "string"}},
            "product_data_discrepancies": {"type": "array", "items": {"type": "string"}},
        },
    }


def merge_research(
    base: ArticleResearchDossier, extra: dict[str, Any] | None
) -> ArticleResearchDossier:
    if not extra:
        return base
    data = json.loads(base.model_dump_json())
    for key in (
        "facts",
        "unknowns_and_risks",
        "editorial_constraints",
        "product_data_discrepancies",
        "reader_takeaways",
        "itinerary_blocks",
    ):
        extra_val = extra.get(key)
        if extra_val:
            data[key] = list(data.get(key) or []) + list(extra_val)
    for key in ("reader_promise", "thesis_and_angle", "genre", "freshness_class"):
        if extra.get(key):
            data[key] = extra[key]
    return ArticleResearchDossier.model_validate(data)


def allowed_fact_texts(dossier: ArticleResearchDossier, ast: DzenArticleAST) -> set[str]:
    allowed = {fact.claim.casefold() for fact in dossier.facts if fact.status == "verified"}
    allowed.add((ast.headline or "").casefold())
    return allowed


__all__ = [
    "ArticleResearchDossier",
    "DossierFact",
    "allowed_fact_texts",
    "catalog_dossier",
    "dossier_json_schema",
    "merge_research",
]
