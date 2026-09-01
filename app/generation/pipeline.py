"""End-to-end article generation.

    Topic → products → context → research → write → verify → strip → review →
    media validation → render → quality gate → draft

The pipeline is budget-aware (it reserves before spending and settles after), records
every claim with its source, and never leaves an unverified volatile fact in the text.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.budget import BudgetManager
from app.ai.router import LLMGateway
from app.analytics.tracking import TrackingService
from app.config import Market, Settings, get_settings
from app.db.enums import (
    ArticleStatus,
    ClaimStatus,
    ClaimType,
    MediaSource,
    TopicStatus,
)
from app.db.models import (
    Article,
    ArticleClaim,
    ArticleMedia,
    ArticleProduct,
    ArticleSource,
    ArticleVersion,
    CostLedgerEntry,
    Product,
    TopicCandidate,
)
from app.db.types import utcnow
from app.errors import BudgetExceeded, LLMError
from app.generation.claims import DetectedClaim, scan_document, strip_unverified
from app.generation.context import ContextBuilder, WriterContext
from app.generation.covers import GeneratedCoverService
from app.generation.product_selection import ProductSelector, RankedProduct
from app.generation.quality import GateResult, QualityGate
from app.generation.research import FactResearchService, VerificationResult
from app.generation.schemas import ArticleDocument, QualityReview
from app.generation.writer import ArticleCritic, ArticleWriter
from app.links.affiliate import AffiliateLinkBuilder, LinkContext
from app.logging_setup import get_logger, job_context, new_job_id
from app.media_assets import MediaCandidate
from app.telegram.media import MediaValidator
from app.telegram.renderer import RenderedArticle, RichMessageRenderer

log = get_logger("generation.pipeline")

MAX_GENERATION_ATTEMPTS = 3


@dataclass(slots=True)
class GenerationOutcome:
    article: Article | None
    status: str
    reason: str = ""
    cost_usd: float = 0.0
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.article is not None and self.status in {
            ArticleStatus.NEEDS_REVIEW,
            ArticleStatus.APPROVED,
            ArticleStatus.SCHEDULED,
            ArticleStatus.PUBLISHED,
        }


class GenerationPipeline:
    def __init__(
        self,
        session: Session,
        gateway: LLMGateway,
        *,
        settings: Settings | None = None,
        media_validator: MediaValidator | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.gateway = gateway
        self.budget = gateway.budget or BudgetManager(session, self.settings)
        self.links = AffiliateLinkBuilder(self.settings)
        self.selector = ProductSelector(self.settings)
        self.context_builder = ContextBuilder(session, self.settings)
        self.writer = ArticleWriter(gateway, self.settings)
        self.critic = ArticleCritic(gateway, self.settings)
        self.research = FactResearchService(session, gateway, settings=self.settings)
        self.gate = QualityGate(self.settings, self.links)
        self.renderer = RichMessageRenderer(settings=self.settings, link_builder=self.links)
        self.media_validator = media_validator or MediaValidator(self.settings)
        self.tracking = TrackingService(session, settings=self.settings, link_builder=self.links)
        self.covers = GeneratedCoverService(gateway.provider, self.budget, settings=self.settings)

    # ------------------------------------------------------------------ main
    def generate(self, topic: TopicCandidate) -> GenerationOutcome:
        market: Market = topic.market  # type: ignore[assignment]
        job_id = new_job_id("gen")

        with job_context(
            "article.generate",
            job_id=job_id,
            market=market,
            topic_id=topic.id,
            entity_type=topic.entity_type,
            entity_id=topic.entity_external_id,
        ) as ctx:
            products = self._select_products(topic, market)
            if not products:
                topic.status = TopicStatus.REJECTED
                topic.status_reason = "no relevant available products"
                ctx["status"] = "skipped"
                return GenerationOutcome(None, "skipped", topic.status_reason)

            context = self.context_builder.build(topic, products)
            estimate = self.budget.estimate_article_cost(
                writer_model=self.settings.openai_writer_model,
                review_model=self.settings.review_model,
                context_chars=len(str(context.as_payload(self.settings))),
                expected_output_chars=self.settings.article_target_max_chars,
                web_search_calls=3 if topic.requires_volatile_facts else 1,
            )
            try:
                reservation = self.budget.reserve(market, estimate, article_id=None, job_id=job_id)
            except BudgetExceeded as exc:
                ctx["status"] = "budget_blocked"
                log.info("generation.budget_blocked", market=market, reason=str(exc))
                return GenerationOutcome(None, "budget_blocked", str(exc))

            article = self._create_article(topic, market, estimate)
            reservation.article_id = article.id
            topic.status = TopicStatus.GENERATING
            self.session.flush()

            try:
                outcome = self._run(article, topic, context, market, job_id)
            except BudgetExceeded as exc:
                self.budget.release(reservation)
                article.status = ArticleStatus.FAILED
                article.status_reason = str(exc)
                topic.status = TopicStatus.CANDIDATE
                self.session.flush()
                return GenerationOutcome(article, "budget_blocked", str(exc))
            except LLMError as exc:
                self.budget.settle(reservation)
                article.status = ArticleStatus.FAILED
                article.status_reason = f"LLM failure: {exc}"
                topic.status = TopicStatus.CANDIDATE
                self.session.flush()
                return GenerationOutcome(article, "failed", str(exc))

            self.budget.settle(reservation)
            ctx["cost_usd"] = round(article.actual_cost_usd, 6)
            ctx["article_id"] = article.id
            ctx["status"] = outcome.status
            return outcome

    def rewrite(self, article: Article) -> GenerationOutcome:
        """Re-run the writer against an existing article (keeps id + Telegram pubs)."""
        topic = article.topic
        if topic is None:
            return GenerationOutcome(None, "failed", "article has no topic to rewrite from")

        market: Market = topic.market  # type: ignore[assignment]
        job_id = new_job_id("rew")
        previous_status = article.status

        with job_context(
            "article.rewrite",
            job_id=job_id,
            market=market,
            topic_id=topic.id,
            article_id=article.id,
            entity_type=topic.entity_type,
            entity_id=topic.entity_external_id,
        ) as ctx:
            products = self._select_products(topic, market)
            if not products:
                ctx["status"] = "skipped"
                return GenerationOutcome(article, "skipped", "no relevant available products")

            context = self.context_builder.build(topic, products)
            estimate = self.budget.estimate_article_cost(
                writer_model=self.settings.openai_writer_model,
                review_model=self.settings.review_model,
                context_chars=len(str(context.as_payload(self.settings))),
                expected_output_chars=self.settings.article_target_max_chars,
                web_search_calls=3 if topic.requires_volatile_facts else 1,
            )
            try:
                reservation = self.budget.reserve(
                    market, estimate, article_id=article.id, job_id=job_id
                )
            except BudgetExceeded as exc:
                ctx["status"] = "budget_blocked"
                return GenerationOutcome(article, "budget_blocked", str(exc))

            article.status = ArticleStatus.GENERATING
            article.status_reason = f"rewriting (was {previous_status})"
            topic.status = TopicStatus.GENERATING
            self.session.flush()

            try:
                outcome = self._run(article, topic, context, market, job_id)
            except BudgetExceeded as exc:
                self.budget.release(reservation)
                article.status = previous_status
                article.status_reason = str(exc)
                topic.status = (
                    TopicStatus.USED
                    if previous_status == ArticleStatus.PUBLISHED
                    else TopicStatus.CANDIDATE
                )
                self.session.flush()
                return GenerationOutcome(article, "budget_blocked", str(exc))
            except LLMError as exc:
                self.budget.settle(reservation)
                article.status = previous_status
                article.status_reason = f"LLM failure during rewrite: {exc}"
                topic.status = (
                    TopicStatus.USED
                    if previous_status == ArticleStatus.PUBLISHED
                    else TopicStatus.CANDIDATE
                )
                self.session.flush()
                return GenerationOutcome(article, "failed", str(exc))

            self.budget.settle(reservation)

            if outcome.ok and previous_status == ArticleStatus.PUBLISHED:
                # Keep the live post identity; content was refreshed in place.
                article.status = ArticleStatus.PUBLISHED
                article.status_reason = "rewritten under current editorial rules"
                topic.status = TopicStatus.USED
                self.session.flush()
                outcome = GenerationOutcome(
                    article,
                    ArticleStatus.PUBLISHED,
                    outcome.reason,
                    outcome.cost_usd,
                    outcome.issues,
                )

            ctx["cost_usd"] = round(article.actual_cost_usd, 6)
            ctx["article_id"] = article.id
            ctx["status"] = outcome.status
            return outcome

    # -------------------------------------------------------------- internals
    def _run(
        self,
        article: Article,
        topic: TopicCandidate,
        context: WriterContext,
        market: Market,
        job_id: str,
    ) -> GenerationOutcome:
        cost = 0.0
        feedback: list[str] = []
        last_issues: list[str] = []
        review: QualityReview | None = None
        document: ArticleDocument | None = None
        verifications: list[VerificationResult] = []
        detected: list[DetectedClaim] = []

        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            article.generation_attempts = attempt
            escalate = attempt >= 3
            written = self.writer.write(
                context,
                article_id=article.id,
                job_id=job_id,
                escalate=escalate,
                feedback=feedback or None,
            )
            cost += written.cost_usd
            document = written.document

            detected = scan_document(
                document, api_facts=context.catalog_facts, market=market
            ).claims
            needs_check = [claim for claim in detected if claim.requires_verification]
            verifications = []
            if needs_check:
                verifications = self.research.verify(
                    needs_check,
                    market=market,
                    entity_name=topic.entity_name,
                    article_id=article.id,
                    job_id=job_id,
                )
                unverified = [result.claim for result in verifications if not result.is_verified]
                if unverified:
                    document, removed = strip_unverified(document, unverified)
                    log.info(
                        "generation.claims_omitted",
                        article_id=article.id,
                        removed=removed,
                        unverified=len(unverified),
                    )
                    context.verified_facts = [
                        {
                            "claim": result.claim,
                            "source_url": result.source_url,
                            "source_title": result.source_title,
                        }
                        for result in verifications
                        if result.is_verified
                    ]

            review, review_cost = self.critic.review(
                document, context, article_id=article.id, job_id=job_id
            )
            cost += review_cost

            gate = self._evaluate(document, context, review, detected, verifications, market)
            last_issues = [*gate.errors, *review.issues]
            if gate.passed:
                break

            log.info(
                "generation.attempt_failed",
                article_id=article.id,
                attempt=attempt,
                issues=gate.errors[:5],
            )
            feedback = gate.errors[:8]
            if attempt < MAX_GENERATION_ATTEMPTS:
                decision = self.budget.can_start_article(market)
                if not decision.allowed:
                    break

        if document is None:
            raise LLMError("writer produced no document")

        rendered = self._render(article, document, context, market)
        gate = self._evaluate(
            document, context, review, detected, verifications, market, rendered=rendered
        )

        self._persist(
            article,
            topic,
            document,
            context,
            rendered,
            review,
            detected,
            verifications,
            cost,
            gate,
        )

        if not gate.passed:
            article.status = ArticleStatus.VALIDATION_FAILED
            article.status_reason = "; ".join(gate.errors[:5])
            topic.generation_failures += 1
            if topic.generation_failures >= self.settings.max_topic_generation_failures:
                # Retire the topic rather than paying for the same failure every run.
                topic.status = TopicStatus.REJECTED
                topic.status_reason = (
                    f"retired after {topic.generation_failures} failed generations: "
                    f"{article.status_reason}"
                )
                log.info(
                    "topics.retired",
                    topic_id=topic.id,
                    market=topic.market,
                    failures=topic.generation_failures,
                    reason=article.status_reason,
                )
            else:
                topic.status = TopicStatus.CANDIDATE
            self.session.flush()
            return GenerationOutcome(
                article, ArticleStatus.VALIDATION_FAILED, article.status_reason, cost, gate.errors
            )

        topic.status = TopicStatus.USED
        topic.generation_failures = 0
        topic.last_used_at = utcnow()
        article.status = ArticleStatus.NEEDS_REVIEW
        article.status_reason = None
        self.session.flush()
        return GenerationOutcome(article, ArticleStatus.NEEDS_REVIEW, "", cost, last_issues)

    def _select_products(self, topic: TopicCandidate, market: Market) -> list[RankedProduct]:
        rows = self.session.scalars(
            select(Product).where(Product.market == market, Product.available.is_(True))
        ).all()
        catalog = {row.external_id: row for row in rows}
        return self.selector.select(topic, catalog)

    def _create_article(self, topic: TopicCandidate, market: Market, estimate: float) -> Article:
        article = Article(
            public_id=secrets.token_urlsafe(8),
            market=market,
            topic_id=topic.id,
            topic_slug=topic.topic_slug,
            entity_type=topic.entity_type,
            entity_external_id=topic.entity_external_id,
            entity_name=topic.entity_name,
            intent=topic.intent,
            primary_query=topic.primary_query,
            secondary_queries=list(topic.secondary_queries or []),
            status=ArticleStatus.GENERATING,
            estimated_cost_usd=estimate,
        )
        self.session.add(article)
        self.session.flush()
        return article

    def _evaluate(
        self,
        document: ArticleDocument,
        context: WriterContext,
        review: QualityReview | None,
        detected: list[DetectedClaim],
        verifications: list[VerificationResult],
        market: Market,
        *,
        rendered: RenderedArticle | None = None,
    ) -> GateResult:
        status_by_claim = {result.claim: result.status for result in verifications}
        remaining = scan_document(document, api_facts=context.catalog_facts).claims
        claim_statuses = [
            (
                claim.text,
                status_by_claim.get(claim.text, ClaimStatus.UNVERIFIED)
                if claim.requires_verification
                else ClaimStatus.VERIFIED,
                claim.is_critical,
            )
            for claim in remaining
        ]
        _ = detected
        return self.gate.evaluate(
            document,
            context,
            review=review,
            claim_statuses=claim_statuses,
            rendered_urls=rendered.urls if rendered else [],
        )

    # ----------------------------------------------------------------- render
    def _render(
        self,
        article: Article,
        document: ArticleDocument,
        context: WriterContext,
        market: Market,
    ) -> RenderedArticle:
        media_by_id = {item.id: item for item in context.media}
        used_ids = {p.media_id for p in document.media_placements}
        cover = next((item for item in context.media if item.role == "cover"), None)
        if cover is not None:
            used_ids.add(cover.id)
        checks = self.media_validator.check_many(
            [
                (media_by_id[mid].url, media_by_id[mid].kind)
                for mid in used_ids
                if mid in media_by_id
            ]
        )
        blocked = {
            mid
            for mid, check in zip([m for m in used_ids if m in media_by_id], checks, strict=False)
            if not check.ok
        }
        for mid, check in zip([m for m in used_ids if m in media_by_id], checks, strict=False):
            if not check.ok:
                log.warning(
                    "generation.media_rejected",
                    article_id=article.id,
                    url=media_by_id[mid].url,
                    error=check.error,
                )

        usable_cover = any(
            item.kind == "photo" and item.id not in blocked for item in context.media
        )
        generated = self.covers.generate(
            market=market,
            entity_name=article.entity_name,
            article_id=article.id,
            api_media_available=usable_cover,
        )
        if generated is not None:
            for item in media_by_id.values():
                if item.role == "cover":
                    item.role = "inline"
            media_by_id[generated.id] = generated
            context.media.append(generated)

        products = {item.product.external_id: item.product for item in context.products}
        link_context = LinkContext(
            market=market, article_id=article.public_id, topic_slug=article.topic_slug
        )
        audio_urls = {item["product_id"]: item["url"] for item in context.audio if item.get("url")}

        def resolver(product_id: str, placement: str) -> str:
            product = products[product_id]
            affiliate_url = self.renderer.cards.product_url(product, market, link_context)
            if not self.settings.use_tracking_redirect:
                return affiliate_url
            tracked = self.tracking.get_or_create(
                article=article,
                market=market,
                target_url=affiliate_url,
                product_external_id=product_id,
                placement=placement,
                entity_type=article.entity_type,
                entity_external_id=article.entity_external_id,
            )
            return tracked.public_url

        return self.renderer.render(
            document,
            market=market,
            products=products,
            media=media_by_id,
            link_context=link_context,
            entity_name=article.entity_name,
            audio_urls=audio_urls,
            url_resolver=resolver,
            blocked_media_ids=blocked,
        )

    # ---------------------------------------------------------------- persist
    def _persist(
        self,
        article: Article,
        topic: TopicCandidate,
        document: ArticleDocument,
        context: WriterContext,
        rendered: RenderedArticle,
        review: QualityReview | None,
        detected: list[DetectedClaim],
        verifications: list[VerificationResult],
        cost: float,
        gate: GateResult,
    ) -> None:
        article.title = document.title
        article.body = document.model_dump()
        article.rendered_message = rendered.message
        article.char_count = document.char_count()
        # Take the cost from the ledger rather than from the pipeline's running total:
        # research and any other side calls are billed there too, so the ledger is the
        # only figure that cannot drift from what was actually spent.
        ledger_total = self.session.scalar(
            select(func.coalesce(func.sum(CostLedgerEntry.amount_usd), 0.0)).where(
                CostLedgerEntry.article_id == article.id
            )
        )
        article.actual_cost_usd = round(float(ledger_total or cost), 6)
        article.validation_issues = [*gate.errors, *gate.warnings][:20]
        if review is not None:
            article.quality_scores = review.model_dump()
            article.quality_score = review.overall
            article.factuality_score = review.factuality
        article.current_version += 1
        article.products_refreshed_at = utcnow()

        article.versions.append(
            ArticleVersion(
                version=article.current_version,
                body=article.body,
                rendered_message=rendered.message,
                quality_scores=article.quality_scores,
                cost_usd=article.actual_cost_usd,
                note=f"attempt {article.generation_attempts}",
            )
        )

        self._replace(article.claims)
        status_by_claim = {result.claim: result for result in verifications}
        for claim in detected:
            result = status_by_claim.get(claim.text)
            still_present = claim.text in document.plain_text()
            if result is not None and not result.is_verified and not still_present:
                status = ClaimStatus.OMITTED
            elif result is not None:
                status = result.status
            elif claim.supported_by_api:
                status = ClaimStatus.VERIFIED
            else:
                status = ClaimStatus.PENDING
            article.claims.append(
                ArticleClaim(
                    claim=claim.text,
                    claim_type=str(
                        ClaimType.WEGOTRIP_API if claim.supported_by_api else claim.claim_type
                    ),
                    category=str(claim.category),
                    requires_verification=claim.requires_verification,
                    status=str(status),
                    source_url=result.source_url if result else None,
                    source_title=result.source_title if result else None,
                    source_tier=result.source_tier if result else None,
                    confidence=result.confidence if result else None,
                    verified_at=utcnow() if status == ClaimStatus.VERIFIED else None,
                    checked_at=utcnow(),
                )
            )

        self._replace(article.sources)
        seen_sources: set[str] = set()
        for result in verifications:
            if result.source_url and result.source_url not in seen_sources:
                seen_sources.add(result.source_url)
                article.sources.append(
                    ArticleSource(
                        url=result.source_url,
                        title=result.source_title,
                        tier=result.source_tier,
                    )
                )

        self._replace(article.products)
        placements = {p.product_id: p for p in document.product_placements}
        for position, item in enumerate(context.products):
            placement = placements.get(item.product.external_id)
            card = next(
                (
                    c
                    for c in rendered.product_cards
                    if c.product_external_id == item.product.external_id
                ),
                None,
            )
            article.products.append(
                ArticleProduct(
                    product_external_id=item.product.external_id,
                    placement=placement.placement if placement else item.placement,
                    position=position,
                    rank_score=item.score,
                    rank_breakdown=item.breakdown,
                    snapshot={
                        "title": item.product.title,
                        "price": item.product.price,
                        "currency": item.product.currency_code,
                        "rating": item.product.rating,
                        "available": item.product.available,
                        "snapshot_id": item.product.snapshot_id,
                    },
                    affiliate_url=self.renderer.cards.product_url(
                        item.product,
                        article.market,  # type: ignore[arg-type]
                        LinkContext(
                            market=article.market,  # type: ignore[arg-type]
                            article_id=article.public_id,
                            topic_slug=article.topic_slug,
                        ),
                    ),
                    tracking_url=card.url if card else None,
                    active=placement is not None,
                )
            )

        self._replace(article.media)
        media_by_id = {item.id: item for item in context.media}
        for position, media_id in enumerate(rendered.used_media_ids):
            candidate: MediaCandidate | None = media_by_id.get(media_id)
            if candidate is None:
                continue
            article.media.append(
                ArticleMedia(
                    media_key=candidate.id,
                    kind=candidate.kind,
                    role=candidate.role,
                    url=candidate.url,
                    source=str(
                        MediaSource.GENERATED
                        if candidate.source_entity_type == "generated"
                        else MediaSource.WEGOTRIP_API
                    ),
                    source_entity_type=candidate.source_entity_type,
                    source_entity_id=candidate.source_entity_id,
                    product_external_id=candidate.product_external_id,
                    caption=candidate.caption,
                    position=position,
                    validated=True,
                )
            )

        _ = topic
        self.session.flush()

    def _replace(self, collection: list[Any]) -> None:
        """Clear a child collection; ``delete-orphan`` removes the rows on flush."""
        collection.clear()
        self.session.flush()


__all__ = ["MAX_GENERATION_ATTEMPTS", "GenerationOutcome", "GenerationPipeline"]
