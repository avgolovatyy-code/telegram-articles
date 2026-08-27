"""Article writer and critic passes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.ai.prompts import CLAIM_EXTRACTOR, review_prompt, writer_prompt
from app.ai.router import LLMGateway
from app.config import Market, Settings, get_settings
from app.db.enums import LLMTask
from app.errors import LLMOutputError
from app.generation.context import WriterContext
from app.generation.schemas import (
    ARTICLE_JSON_SCHEMA,
    CLAIM_EXTRACTION_JSON_SCHEMA,
    QUALITY_REVIEW_JSON_SCHEMA,
    ArticleDocument,
    DraftClaim,
    QualityReview,
)
from app.logging_setup import get_logger

log = get_logger("generation.writer")


@dataclass(slots=True)
class WriterOutcome:
    document: ArticleDocument
    cost_usd: float
    model: str


class ArticleWriter:
    def __init__(self, gateway: LLMGateway, settings: Settings | None = None) -> None:
        self.gateway = gateway
        self.settings = settings or get_settings()

    def write(
        self,
        context: WriterContext,
        *,
        article_id: int | None = None,
        job_id: str | None = None,
        escalate: bool = False,
        feedback: list[str] | None = None,
    ) -> WriterOutcome:
        payload = context.as_payload(self.settings)
        if feedback:
            payload["previous_review_issues"] = feedback
        market: Market = context.market

        outcome = self.gateway.run(
            task=LLMTask.ARTICLE_WRITE,
            prompt=writer_prompt(market),
            payload=json.dumps(payload, ensure_ascii=False),
            json_schema=ARTICLE_JSON_SCHEMA,
            schema_name="article",
            market=market,
            article_id=article_id,
            topic_id=context.topic.id,
            job_id=job_id,
            escalate=escalate,
            max_output_tokens=8000,
        )
        parsed = outcome.response.parsed
        if not isinstance(parsed, dict):
            raise LLMOutputError("Writer did not return a JSON object")
        document = ArticleDocument.model_validate(parsed)
        _sanitize(document, context)
        return WriterOutcome(
            document=document, cost_usd=outcome.cost_usd, model=outcome.response.model
        )


class ArticleCritic:
    def __init__(self, gateway: LLMGateway, settings: Settings | None = None) -> None:
        self.gateway = gateway
        self.settings = settings or get_settings()

    def review(
        self,
        document: ArticleDocument,
        context: WriterContext,
        *,
        article_id: int | None = None,
        job_id: str | None = None,
    ) -> tuple[QualityReview, float]:
        payload = json.dumps(
            {
                "market": context.market,
                "primary_query": context.topic.primary_query,
                "secondary_queries": list(context.topic.secondary_queries or []),
                "allowed_products": [item.product.external_id for item in context.products],
                "catalog_facts": context.catalog_facts,
                "verified_facts": context.verified_facts,
                "article": document.model_dump(),
            },
            ensure_ascii=False,
        )
        outcome = self.gateway.run(
            task=LLMTask.QUALITY_REVIEW,
            prompt=review_prompt(context.market),
            payload=payload,
            json_schema=QUALITY_REVIEW_JSON_SCHEMA,
            schema_name="quality_review",
            market=context.market,
            article_id=article_id,
            job_id=job_id,
            max_output_tokens=1200,
        )
        parsed = outcome.response.parsed
        if not isinstance(parsed, dict):
            raise LLMOutputError("Critic did not return a JSON object")
        return QualityReview.model_validate(parsed), outcome.cost_usd


class ClaimExtractor:
    """Second-opinion extraction on top of the deterministic scanner."""

    def __init__(self, gateway: LLMGateway) -> None:
        self.gateway = gateway

    def extract(
        self,
        document: ArticleDocument,
        *,
        market: Market,
        article_id: int | None = None,
        job_id: str | None = None,
    ) -> tuple[list[DraftClaim], float]:
        outcome = self.gateway.run(
            task=LLMTask.CLAIM_EXTRACTION,
            prompt=CLAIM_EXTRACTOR,
            payload=json.dumps(
                {"market": market, "text": document.plain_text()}, ensure_ascii=False
            ),
            json_schema=CLAIM_EXTRACTION_JSON_SCHEMA,
            schema_name="claim_extraction",
            market=market,
            article_id=article_id,
            job_id=job_id,
            max_output_tokens=2000,
        )
        parsed = outcome.response.parsed or {}
        claims = [
            DraftClaim.model_validate(item)
            for item in parsed.get("claims", [])
            if isinstance(item, dict)
        ]
        return claims, outcome.cost_usd


def _sanitize(document: ArticleDocument, context: WriterContext) -> None:
    """Drop anything the model invented: unknown products, unknown media, stray URLs."""
    allowed_products = {item.product.external_id for item in context.products}
    allowed_media = {item.id for item in context.media}
    allowed_audio = {item["product_id"] for item in context.audio}

    document.product_placements = [
        placement
        for placement in document.product_placements
        if placement.product_id in allowed_products
    ]
    document.media_placements = [
        placement for placement in document.media_placements if placement.media_id in allowed_media
    ]
    document.audio_placements = [
        placement
        for placement in document.audio_placements
        if placement.product_id in allowed_audio
    ]

    seen_products: set[str] = set()
    unique: list = []
    for placement in document.product_placements:
        if placement.product_id in seen_products:
            continue
        seen_products.add(placement.product_id)
        unique.append(placement)
    document.product_placements = unique

    for section in document.sections:
        for block in section.blocks:
            if block.text:
                block.text = _strip_urls(block.text)
            block.items = [_strip_urls(item) for item in block.items]
    document.intro = _strip_urls(document.intro)
    if document.closing:
        document.closing = _strip_urls(document.closing)


_URL_MARKERS = ("http://", "https://", "www.", "wegotrip.com", "wegotrip.ru")


def _strip_urls(text: str) -> str:
    """The writer must never emit links; the renderer owns every URL."""
    if not any(marker in text.lower() for marker in _URL_MARKERS):
        return text
    words = [
        word for word in text.split() if not any(marker in word.lower() for marker in _URL_MARKERS)
    ]
    return " ".join(words).strip()


__all__ = ["ArticleCritic", "ArticleWriter", "ClaimExtractor", "WriterOutcome"]
