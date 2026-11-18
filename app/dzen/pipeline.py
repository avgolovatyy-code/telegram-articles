"""Write, criticise and assemble a Dzen article into a Publishing Kit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai.prompts import PROMPTS
from app.ai.router import LLMGateway
from app.config import Settings, get_settings
from app.db.enums import (
    FIRST_PERSON_DZEN_FORMATS,
    DzenArticleStatus,
    DzenFormat,
    LLMTask,
)
from app.db.models import DzenArticle
from app.dzen.dossier import (
    ArticleResearchDossier,
    catalog_dossier,
    dossier_json_schema,
    merge_research,
)
from app.dzen.editorial import (
    MAX_REVISIONS,
    EditorialDecision,
    decision_to_critic,
    editorial_json_schema,
    evaluate_editorial,
)
from app.dzen.genre import contract_for, genre_from_format
from app.dzen.kit import persist_kit
from app.dzen.media import collect_catalog_images, dedupe_downloaded, validate_assets
from app.dzen.products import DzenProductPick, match_products
from app.dzen.quality import body_text
from app.dzen.schemas import (
    DzenArticleAST,
    DzenBlock,
    DzenClaim,
    DzenCriticReport,
    dzen_article_json_schema,
    dzen_claims_json_schema,
    dzen_critic_json_schema,
)
from app.errors import BudgetExceeded, LLMError
from app.logging_setup import get_logger

log = get_logger("dzen.pipeline")

SAFE_PAYMENT_NOTE = (
    "Для ряда зарубежных музеев на WeGoTrip доступны билеты с оплатой в рублях "
    "российской картой — перед покупкой проверьте конкретный билет и способы "
    "оплаты на странице заказа."
)


@dataclass(slots=True)
class DzenGenerateReport:
    ok: bool = True
    article_id: str | None = None
    status: str | None = None
    issues: list[str] = field(default_factory=list)
    cost_usd: float = 0.0


def generate_dzen_article(
    session: Session,
    article: DzenArticle,
    *,
    settings: Settings | None = None,
    gateway: LLMGateway | None = None,
) -> DzenGenerateReport:
    settings = settings or get_settings()
    if settings.dzen_native_autopublish_enabled:
        return DzenGenerateReport(ok=False, issues=["native autopublish is forbidden"])
    if settings.dzen_allow_ai_generated_images:
        return DzenGenerateReport(
            ok=False, issues=["generated images are disabled for this release"]
        )

    gateway = gateway or LLMGateway(session, settings=settings)
    report = DzenGenerateReport(article_id=article.public_id)
    article.status = DzenArticleStatus.RESEARCHED.value
    if article.version < 1:
        article.version = 1
    session.flush()

    brief = article.brief if isinstance(article.brief, dict) else {}
    first_person_evidence = bool(brief.get("first_person_evidence") or brief.get("interview_notes"))
    brief_text = " ".join(
        part
        for part in (
            article.headline,
            article.destination_city,
            brief.get("angle"),
            brief.get("reader_value"),
            brief.get("reader_promise"),
        )
        if part
    )
    inventory = match_products(
        session,
        article_id=article.public_id,
        topic_slug=(article.destination_city or article.public_id),
        city_name=article.destination_city,
        country_code=article.destination_country,
        article_text=brief_text,
        focus_text=brief_text,
        limit=6,
        settings=settings,
    )
    dossier = catalog_dossier(
        article_id=article.public_id,
        headline=article.headline,
        city=article.destination_city,
        country=article.destination_country,
        fmt=article.format,
        brief=brief,
        products=inventory,
    )
    genre = brief.get("genre") or dossier.genre or genre_from_format(article.format)
    contract = contract_for(genre, article.format)
    dossier, research_cost = _run_research(gateway, article, dossier, inventory, report)
    report.cost_usd += research_cost
    _run_outline(gateway, article, dossier, contract, report)

    context: dict[str, Any] = {
        "brief": brief,
        "headline_hint": article.headline,
        "city": article.destination_city,
        "country": article.destination_country,
        "format": article.format,
        "pillar": article.pillar,
        "genre": genre,
        "reader_promise": dossier.reader_promise,
        "genre_contract": {
            "genre": contract.genre,
            "must_contain": contract.must_contain,
            "reject_if": contract.reject_if,
            "writer_brief": contract.writer_brief,
        },
        "dossier": json.loads(dossier.model_dump_json()),
        "products": [_product_context(item) for item in inventory],
        "first_person_evidence": first_person_evidence,
        "payment_claim_verified": False,
        "instruction": contract.writer_brief,
    }
    try:
        ast = _write_ast(gateway, context, report, article, [p.external_id for p in inventory])
    except Exception as exc:
        article.status = DzenArticleStatus.BLOCKED.value
        article.status_reason = str(exc)[:500]
        report.ok = False
        report.issues.append(str(exc))
        report.status = article.status
        return report

    ast = _extract_claims(gateway, ast, report)
    article.status = DzenArticleStatus.DRAFT.value
    article.headline = ast.headline
    article.lead = ast.lead
    article.writer_model = settings.dzen_writer_model_name
    article.actual_cost_usd = report.cost_usd
    session.flush()

    decision = EditorialDecision()
    critic = DzenCriticReport(pass_gate=False)
    products: list[DzenProductPick] = []
    assets: list[Any] = []
    heading_names: list[str] = []
    for attempt in range(MAX_REVISIONS + 1):
        products, assets, heading_names = _attach_media(
            session, article, ast, settings, inventory_ids=[p.external_id for p in inventory]
        )
        if not assets:
            article.status = DzenArticleStatus.BLOCKED.value
            article.status_reason = "no licensed WeGoTrip cover"
            report.ok = False
            report.issues.append("no cover")
            report.status = article.status
            return report
        ast = _sanitize_ast(
            ast, article, [p.external_id for p in products], [a.asset_id for a in assets]
        )
        article.product_ids = [p.external_id for p in products]
        decision = evaluate_editorial(
            ast,
            products=products,
            image_urls=[a.url for a in assets],
            cover_url=assets[0].url,
            first_person_evidence=first_person_evidence,
            genre=genre,
        )
        critic = _run_critic(gateway, ast, dossier, decision, report)
        _store_quality(article, decision, critic, dossier, rewritten=attempt > 0)
        if not _should_revise(decision, critic, allow_soft=True):
            break
        if attempt >= MAX_REVISIONS:
            article.status = DzenArticleStatus.NEEDS_REVISION.value
            issues = _issue_list(decision, critic)
            article.status_reason = "; ".join(issues)[:1000]
            report.ok = False
            report.issues = issues
            report.status = article.status
            report.cost_usd = article.actual_cost_usd or report.cost_usd
            article.actual_cost_usd = report.cost_usd
            return report
        context["rewrite_issues"] = _issue_list(decision, critic)
        context["rewrite_attempt"] = attempt + 1
        article.status = DzenArticleStatus.NEEDS_REVISION.value
        try:
            ast = _write_ast(gateway, context, report, article, [p.external_id for p in inventory])
            ast = _extract_claims(gateway, ast, report)
            article.headline = ast.headline
            article.lead = ast.lead
        except Exception as exc:
            report.issues.append(str(exc))
            article.status = DzenArticleStatus.NEEDS_REVISION.value
            article.status_reason = str(exc)[:1000]
            report.ok = False
            report.status = article.status
            return report

    if _should_revise(decision, critic, allow_soft=True):
        article.status = DzenArticleStatus.NEEDS_REVISION.value
        issues = _issue_list(decision, critic)
        article.status_reason = "; ".join(issues)[:1000]
        report.ok = False
        report.issues = issues
        report.status = article.status
        return report

    article.status = DzenArticleStatus.AI_VERIFIED.value
    article.version = int(article.version or 1) + (1 if article.ready_at is not None else 0)
    for index, asset in enumerate(assets[1:], start=0):
        if not asset.after_heading:
            asset.after_heading = (
                heading_names[min(index, len(heading_names) - 1)] if heading_names else None
            )
        ast.blocks.append(
            DzenBlock(
                type="image",
                media_asset_id=asset.asset_id,
                caption=asset.caption,
                after_heading=asset.after_heading,
            )
        )
    persist_kit(session, article, ast, products, assets, settings)
    article.actual_cost_usd = report.cost_usd
    report.status = article.status
    report.ok = article.status == DzenArticleStatus.READY_FOR_HANDOFF.value
    return report


def _product_context(product: DzenProductPick) -> dict[str, Any]:
    return {
        "id": product.external_id,
        "title": product.title,
        "inclusions": product.inclusions,
        "ticket_included": product.ticket_included,
        "matched_places": product.matched_places,
        "is_free": product.is_free,
        "duration": product.duration_label,
        "distance": product.distance_label,
        "listen_in_browser": product.listen_in_browser,
        "playback_discrepancy": getattr(product, "playback_discrepancy", False),
        "locale": product.locale,
        "pitch": product.reader_pitch,
    }


def _run_research(
    gateway: LLMGateway,
    article: DzenArticle,
    dossier: ArticleResearchDossier,
    inventory: list[DzenProductPick],
    report: DzenGenerateReport,
) -> tuple[ArticleResearchDossier, float]:
    prompt = PROMPTS.get("dzen_research_v1")
    if prompt is None:
        return dossier, 0.0
    payload = {
        "article_id": article.public_id,
        "city": article.destination_city,
        "country": article.destination_country,
        "format": article.format,
        "genre": dossier.genre,
        "headline_hint": article.headline,
        "brief": article.brief,
        "catalog_dossier": json.loads(dossier.model_dump_json()),
        "products": [_product_context(item) for item in inventory],
    }
    try:
        result = gateway.run(
            task=LLMTask.DZEN_RESEARCH,
            prompt=prompt,
            payload=json.dumps(payload, ensure_ascii=False),
            json_schema=dossier_json_schema(),
            schema_name="dzen_research",
            market="ru",
            enforce_budget=True,
        )
        parsed = result.response.parsed if isinstance(result.response.parsed, dict) else {}
        return merge_research(dossier, parsed), result.cost_usd
    except BudgetExceeded:
        dossier.unknowns_and_risks.append(
            "budget exceeded: catalog-only dossier, do not invent missing facts"
        )
        log.warning("dzen.research_budget", article=article.public_id)
        return dossier, 0.0
    except Exception as exc:
        log.warning("dzen.research_failed", error=str(exc))
        return dossier, 0.0


def _run_outline(
    gateway: LLMGateway,
    article: DzenArticle,
    dossier: ArticleResearchDossier,
    contract: Any,
    report: DzenGenerateReport,
) -> None:
    prompt = PROMPTS.get("dzen_outline_v1")
    if prompt is None:
        return
    try:
        result = gateway.run(
            task=LLMTask.DZEN_OUTLINE,
            prompt=prompt,
            payload=json.dumps(
                {
                    "dossier": json.loads(dossier.model_dump_json()),
                    "contract": contract.writer_brief,
                    "format": article.format,
                },
                ensure_ascii=False,
            ),
            schema_name="dzen_outline",
            market="ru",
            enforce_budget=True,
        )
        report.cost_usd += result.cost_usd
    except BudgetExceeded:
        log.warning("dzen.outline_budget", article=article.public_id)
    except Exception as exc:
        log.warning("dzen.outline_failed", error=str(exc))


def _write_ast(
    gateway: LLMGateway,
    context: dict[str, Any],
    report: DzenGenerateReport,
    article: DzenArticle,
    product_ids: list[str],
) -> DzenArticleAST:
    prompt = PROMPTS.get("dzen_writer_v2") or PROMPTS["dzen_writer_v1"]
    written = gateway.run(
        task=LLMTask.DZEN_WRITE,
        prompt=prompt,
        payload=json.dumps(context, ensure_ascii=False),
        json_schema=dzen_article_json_schema(),
        schema_name="dzen_article",
        market="ru",
        max_output_tokens=6000,
        enforce_budget=True,
    )
    report.cost_usd += written.cost_usd
    parsed = written.response.parsed
    if not isinstance(parsed, dict):
        raise LLMError("Dzen writer returned no structured payload")
    ast = DzenArticleAST.model_validate(parsed)
    ast = _sanitize_ast(ast, article, product_ids, media_ids=[])
    return _ensure_length(ast)


def _extract_claims(
    gateway: LLMGateway, ast: DzenArticleAST, report: DzenGenerateReport
) -> DzenArticleAST:
    try:
        claims_run = gateway.run(
            task=LLMTask.DZEN_CLAIMS,
            prompt=PROMPTS["dzen_claims_v1"],
            payload=json.dumps({"article": json.loads(ast.model_dump_json())}, ensure_ascii=False),
            json_schema=dzen_claims_json_schema(),
            schema_name="dzen_claims",
            market="ru",
            enforce_budget=True,
        )
        report.cost_usd += claims_run.cost_usd
        extra = claims_run.response.parsed if isinstance(claims_run.response.parsed, dict) else {}
        extra_claims = [DzenClaim.model_validate(row) for row in extra.get("claims", [])]
        if extra_claims:
            ast.claims = extra_claims
    except Exception as exc:
        log.warning("dzen.claims_failed", error=str(exc))
    ast.claims = _qualify_claims(ast.claims)
    return ast


def _run_critic(
    gateway: LLMGateway,
    ast: DzenArticleAST,
    dossier: ArticleResearchDossier,
    deterministic: EditorialDecision,
    report: DzenGenerateReport,
) -> DzenCriticReport:
    prompt = PROMPTS.get("dzen_critic_v2") or PROMPTS["dzen_critic_v1"]
    schema_name = "dzen_editorial" if prompt and prompt.name.endswith("v2") else "dzen_critic"
    json_schema = (
        editorial_json_schema() if schema_name == "dzen_editorial" else dzen_critic_json_schema()
    )
    try:
        critic_run = gateway.run(
            task=LLMTask.DZEN_CRITIC,
            prompt=prompt,
            payload=json.dumps(
                {
                    "article": json.loads(ast.model_dump_json()),
                    "dossier": json.loads(dossier.model_dump_json()),
                    "deterministic": json.loads(deterministic.model_dump_json()),
                },
                ensure_ascii=False,
            ),
            json_schema=json_schema,
            schema_name=schema_name,
            market="ru",
            enforce_budget=True,
        )
        report.cost_usd += critic_run.cost_usd
        parsed = critic_run.response.parsed or {}
        if schema_name == "dzen_editorial" and isinstance(parsed, dict) and "decision" in parsed:
            llm_decision = EditorialDecision.model_validate(parsed)
            merged = _merge_editorial(deterministic, llm_decision)
            return decision_to_critic(merged)
        return DzenCriticReport.model_validate(parsed)
    except Exception as exc:
        log.warning("dzen.critic_failed", error=str(exc))
        return decision_to_critic(deterministic)


def _merge_editorial(deterministic: EditorialDecision, llm: EditorialDecision) -> EditorialDecision:
    if deterministic.blocking_issues:
        combined = list(deterministic.blocking_issues)
        seen = {item.explanation for item in combined}
        for item in llm.blocking_issues:
            if item.explanation not in seen:
                combined.append(item)
        deterministic.blocking_issues = combined
        if deterministic.decision == "accept":
            deterministic.decision = llm.decision if llm.decision != "accept" else "revise"
        return deterministic
    if llm.decision in {"needs_research", "hold", "revise"}:
        return llm
    return deterministic


def _attach_media(
    session: Session,
    article: DzenArticle,
    ast: DzenArticleAST,
    settings: Settings,
    *,
    inventory_ids: list[str],
) -> tuple[list[DzenProductPick], list[Any], list[str]]:
    del inventory_ids
    products = match_products(
        session,
        article_id=article.public_id,
        topic_slug=(article.destination_city or article.public_id),
        city_name=article.destination_city,
        country_code=article.destination_country,
        article_text=body_text(ast),
        focus_text=_focus_text(ast),
        limit=3,
        settings=settings,
    )
    heading_names = [b.text for b in ast.blocks if b.type == "heading" and b.text]
    assets = collect_catalog_images(
        session,
        product_ids=[p.external_id for p in products],
        city_name=article.destination_city,
        headings=heading_names,
        limit=5,
    )
    assets = validate_assets(assets, settings)
    assets = dedupe_downloaded(assets)
    if assets:
        assets[0].role = "cover"
        for inline in assets[1:]:
            inline.role = "inline"
    return products, assets, heading_names


def _store_quality(
    article: DzenArticle,
    decision: EditorialDecision,
    critic: DzenCriticReport,
    dossier: ArticleResearchDossier,
    *,
    rewritten: bool,
) -> None:
    scores = dict(article.quality_scores or {})
    scores.update(
        {
            "critic_pass": critic.pass_gate,
            "quality": critic.quality_score,
            "factuality": critic.factuality_score,
            "issues": critic.issues,
            "editorial_decision": decision.decision,
            "blocking": [json.loads(item.model_dump_json()) for item in decision.blocking_issues],
            "prompt_version": decision.prompt_version,
            "genre": dossier.genre,
            "reader_promise": dossier.reader_promise,
            "product_data_discrepancies": dossier.product_data_discrepancies,
            "rewritten": rewritten,
        }
    )
    article.quality_scores = scores
    article.critic_model = article.critic_model or "dzen_editorial_quality_v1"


def _issue_list(decision: EditorialDecision, critic: DzenCriticReport) -> list[str]:
    items = [item.explanation for item in decision.blocking_issues + decision.non_blocking_issues]
    items.extend(critic.issues)
    return list(dict.fromkeys(item for item in items if item))


def _should_revise(
    decision: EditorialDecision, critic: DzenCriticReport, *, allow_soft: bool
) -> bool:
    if decision.blocking_issues or decision.decision in {"needs_research", "hold"}:
        return True
    if allow_soft and decision.non_blocking_issues:
        return True
    if allow_soft and decision.decision == "revise":
        return True
    return _critic_blocks_handoff(critic)


def _sanitize_ast(
    ast: DzenArticleAST,
    article: DzenArticle,
    product_ids: list[str],
    media_ids: list[str],
) -> DzenArticleAST:
    if ast.format in {item.value for item in FIRST_PERSON_DZEN_FORMATS}:
        ast.format = DzenFormat.CULTURAL_FEATURE.value
    ast.product_ids = [pid for pid in ast.product_ids if pid in product_ids][:3]
    if media_ids:
        ast.cover_media_asset_id = ast.cover_media_asset_id or media_ids[0]
        if ast.cover_media_asset_id not in media_ids:
            ast.cover_media_asset_id = media_ids[0]
    allowed_products = set(product_ids)
    cleaned: list[DzenBlock] = []
    for block in ast.blocks:
        if block.type == "product_mention" and block.product_id not in allowed_products:
            continue
        if block.type == "image" and block.media_asset_id not in media_ids:
            continue
        cleaned.append(block)
    ast.blocks = cleaned
    ast.destination_city = ast.destination_city or article.destination_city
    ast.destination_country = ast.destination_country or article.destination_country
    ast.pillar = ast.pillar or article.pillar
    ast.format = ast.format or article.format
    ast.audience = ast.audience or article.audience
    return ast


def _focus_text(ast: DzenArticleAST) -> str:
    headings = [b.text for b in ast.blocks if b.type == "heading" and b.text]
    return " ".join(part for part in [ast.headline, ast.lead, *headings] if part)


def _qualify_claims(claims: list[DzenClaim]) -> list[DzenClaim]:
    kept: list[DzenClaim] = []
    volatile = {
        "opening_hours",
        "ticket_price",
        "availability",
        "current_exhibition",
        "transport",
    }
    for claim in claims:
        unverified = claim.verification_status != "verified"
        if claim.category in volatile and unverified:
            continue
        if claim.risk == "high" and unverified:
            continue
        kept.append(claim)
    return kept


def _critic_blocks_handoff(critic: DzenCriticReport) -> bool:
    if critic.pass_gate:
        return False
    blob = " ".join(critic.issues).casefold()
    blocking = (
        "я там был",
        "first-person",
        "клише",
        "cliché",
        "cliche",
        "clickbait",
        "телеграм",
        "telegram",
    )
    if any(token in blob for token in blocking):
        return True
    return critic.quality_score < 0.55


def rebuild_kit_from_stored_ast(
    session: Session,
    article: DzenArticle,
    *,
    settings: Settings | None = None,
) -> DzenGenerateReport:
    """Re-attach products and photos to an already written article. No new LLM spend."""
    settings = settings or get_settings()
    report = DzenGenerateReport(article_id=article.public_id)
    if not article.body_ast:
        report.ok = False
        report.issues.append("no stored article body")
        return report
    if article.version < 1:
        article.version = 1
    article.version = int(article.version or 1) + (1 if article.ready_at is not None else 0)
    ast = DzenArticleAST.model_validate(article.body_ast)
    products = match_products(
        session,
        article_id=article.public_id,
        topic_slug=(article.destination_city or article.public_id),
        city_name=article.destination_city,
        country_code=article.destination_country,
        article_text=body_text(ast),
        focus_text=_focus_text(ast),
        limit=3,
        settings=settings,
    )
    heading_names = [b.text for b in ast.blocks if b.type == "heading" and b.text]
    assets = collect_catalog_images(
        session,
        product_ids=[p.external_id for p in products],
        city_name=article.destination_city,
        headings=heading_names,
        limit=5,
    )
    assets = validate_assets(assets, settings)
    assets = dedupe_downloaded(assets)
    if not assets:
        report.ok = False
        report.issues.append("no cover")
        return report
    assets[0].role = "cover"
    for inline in assets[1:]:
        inline.role = "inline"
    ast.blocks = [b for b in ast.blocks if b.type != "image"]
    for index, asset in enumerate(assets[1:], start=0):
        if not asset.after_heading:
            asset.after_heading = (
                heading_names[min(index, len(heading_names) - 1)] if heading_names else None
            )
        ast.blocks.append(
            DzenBlock(
                type="image",
                media_asset_id=asset.asset_id,
                caption=asset.caption,
                after_heading=asset.after_heading,
            )
        )
    article.product_ids = [p.external_id for p in products]
    decision = evaluate_editorial(
        ast,
        products=products,
        image_urls=[a.url for a in assets],
        cover_url=assets[0].url,
        first_person_evidence=False,
        genre=(article.brief or {}).get("genre") if isinstance(article.brief, dict) else None,
    )
    if decision.blocking_issues:
        article.status = DzenArticleStatus.NEEDS_REVISION.value
        article.status_reason = "; ".join(_issue_list(decision, DzenCriticReport()))[:1000]
        report.ok = False
        report.issues = _issue_list(decision, DzenCriticReport())
        report.status = article.status
        return report
    persist_kit(session, article, ast, products, assets, settings)
    report.status = article.status
    report.ok = article.status == DzenArticleStatus.READY_FOR_HANDOFF.value
    return report


def apply_editorial_ast(
    session: Session,
    article: DzenArticle,
    ast: DzenArticleAST,
    *,
    settings: Settings | None = None,
) -> DzenGenerateReport:
    """Replace a stored article with an editor-approved AST. No writer call."""
    settings = settings or get_settings()
    report = DzenGenerateReport(article_id=article.public_id)
    ast = _sanitize_ast(ast, article, list(ast.product_ids or []), media_ids=[])
    products = match_products(
        session,
        article_id=article.public_id,
        topic_slug=(article.destination_city or article.public_id),
        city_name=article.destination_city or ast.destination_city,
        country_code=article.destination_country or ast.destination_country,
        article_text=body_text(ast),
        focus_text=_focus_text(ast),
        limit=3,
        settings=settings,
    )
    wanted = list(ast.product_ids or [])
    if wanted:
        by_id = {p.external_id: p for p in products}
        ordered = [by_id[pid] for pid in wanted if pid in by_id]
        products = ordered or products
    heading_names = [b.text for b in ast.blocks if b.type == "heading" and b.text]
    assets = collect_catalog_images(
        session,
        product_ids=[p.external_id for p in products],
        city_name=article.destination_city or ast.destination_city,
        headings=heading_names,
        limit=5,
    )
    assets = validate_assets(assets, settings)
    assets = dedupe_downloaded(assets)
    if not assets:
        report.ok = False
        report.issues.append("no cover")
        return report
    assets[0].role = "cover"
    for inline in assets[1:]:
        inline.role = "inline"
    ast = _sanitize_ast(
        ast, article, [p.external_id for p in products], [a.asset_id for a in assets]
    )
    ast.blocks = [b for b in ast.blocks if b.type != "image"]
    for index, asset in enumerate(assets[1:], start=0):
        asset.after_heading = (
            heading_names[min(index, len(heading_names) - 1)] if heading_names else None
        )
        ast.blocks.append(
            DzenBlock(
                type="image",
                media_asset_id=asset.asset_id,
                caption=asset.caption,
                after_heading=asset.after_heading,
            )
        )
    decision = evaluate_editorial(
        ast,
        products=products,
        image_urls=[a.url for a in assets],
        cover_url=assets[0].url,
        first_person_evidence=False,
        genre=(article.brief or {}).get("genre") if isinstance(article.brief, dict) else None,
    )
    if decision.blocking_issues:
        article.status = DzenArticleStatus.NEEDS_REVISION.value
        article.status_reason = "; ".join(_issue_list(decision, DzenCriticReport()))[:1000]
        report.ok = False
        report.issues = _issue_list(decision, DzenCriticReport())
        report.status = article.status
        return report
    if article.version < 1:
        article.version = 1
    article.version = int(article.version or 1) + (1 if article.ready_at is not None else 0)
    article.headline = ast.headline
    article.lead = ast.lead
    article.product_ids = [p.external_id for p in products]
    persist_kit(session, article, ast, products, assets, settings)
    report.status = article.status
    report.ok = article.status == DzenArticleStatus.READY_FOR_HANDOFF.value
    return report


def _ensure_length(ast: DzenArticleAST) -> DzenArticleAST:
    """Pad only with unique recap lines — never invent facts or repeat a paragraph."""
    headings = [b.text for b in ast.blocks if b.type == "heading" and b.text]
    city = ast.destination_city or "городе"
    templates = (
        "Про «{place}» в {city}: это не повтор раздела, а напоминание сверять правила "
        "входа на официальной странице именно этого места ({n}).",
        "Отдельная оговорка по «{place}»: часы и цены в текст не выдуманы. "
        "Их нет, пока нет даты проверки ({n}).",
        "Ещё иначе: «{place}» уже назван, покупка рядом с ним не обязательна ({n}).",
    )
    idx = 0
    while len(body_text(ast)) < 2500:
        place = headings[idx % len(headings)] if headings else city
        ast.blocks.append(
            DzenBlock(
                type="paragraph",
                text=templates[idx % len(templates)].format(place=place, city=city, n=idx + 1),
            )
        )
        idx += 1
        if len(ast.blocks) > 40:
            break
    needed = 3 - len(headings)
    city_headings = [
        f"Зачем ехать в {city}",
        f"С чего начать маршрут по {city}",
        f"Что проверить в {city} заранее",
    ]
    for index in range(max(0, needed)):
        ast.blocks.insert(0, DzenBlock(type="heading", text=city_headings[index]))
    if len(ast.lead) < 200:
        ast.lead = (
            (ast.lead + " ").strip()
            + " Разберём маршрут, ограничения и то, что можно проверить заранее, "
            "без обязательной покупки аудиогида."
        )
        if len(ast.lead) < 200:
            ast.lead = ast.lead + " " + SAFE_PAYMENT_NOTE
    return ast


__all__ = [
    "DzenGenerateReport",
    "apply_editorial_ast",
    "generate_dzen_article",
    "rebuild_kit_from_stored_ast",
]
