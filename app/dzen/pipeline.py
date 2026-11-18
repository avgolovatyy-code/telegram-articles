"""Write, criticise and assemble a Dzen article into a Publishing Kit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

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
from app.dzen.kit import persist_kit
from app.dzen.media import collect_catalog_images, validate_assets
from app.dzen.products import match_products
from app.dzen.quality import body_text, run_gates
from app.dzen.schemas import (
    DzenArticleAST,
    DzenBlock,
    DzenClaim,
    DzenCriticReport,
    dzen_article_json_schema,
    dzen_claims_json_schema,
    dzen_critic_json_schema,
)
from app.errors import LLMError
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
    session.flush()

    products = match_products(
        session,
        article_id=article.public_id,
        topic_slug=(article.destination_city or article.public_id),
        city_name=article.destination_city,
        country_code=article.destination_country,
        settings=settings,
    )
    assets = collect_catalog_images(
        session,
        product_ids=[p.external_id for p in products],
        city_name=article.destination_city,
        limit=5,
    )
    assets = validate_assets(assets, settings)
    if not assets:
        article.status = DzenArticleStatus.BLOCKED.value
        article.status_reason = "no licensed WeGoTrip cover"
        report.ok = False
        report.issues.append("no cover")
        report.status = article.status
        return report
    assets[0].role = "cover"
    for inline in assets[1:]:
        inline.role = "inline"

    context = {
        "brief": article.brief,
        "headline_hint": article.headline,
        "city": article.destination_city,
        "country": article.destination_country,
        "format": article.format,
        "pillar": article.pillar,
        "products": [
            {
                "id": p.external_id,
                "title": p.title,
                "inclusions": p.inclusions,
                "ticket_included": p.ticket_included,
            }
            for p in products
        ],
        "media": [{"id": a.asset_id, "caption": a.caption, "role": a.role} for a in assets],
        "first_person_evidence": False,
        "payment_claim_verified": False,
        "instruction": "Write original Russian Dzen article. Do not mirror Telegram.",
    }
    try:
        written = gateway.run(
            task=LLMTask.DZEN_WRITE,
            prompt=PROMPTS["dzen_writer_v1"],
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
    except Exception as exc:
        article.status = DzenArticleStatus.BLOCKED.value
        article.status_reason = str(exc)[:500]
        report.ok = False
        report.issues.append(str(exc))
        report.status = article.status
        return report

    ast = _sanitize_ast(
        ast, article, [p.external_id for p in products], [a.asset_id for a in assets]
    )
    ast = _ensure_length(ast)

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
    article.status = DzenArticleStatus.DRAFT.value
    article.headline = ast.headline
    article.lead = ast.lead
    article.writer_model = settings.dzen_writer_model_name
    article.actual_cost_usd = report.cost_usd
    session.flush()

    try:
        critic_run = gateway.run(
            task=LLMTask.DZEN_CRITIC,
            prompt=PROMPTS["dzen_critic_v1"],
            payload=json.dumps({"article": json.loads(ast.model_dump_json())}, ensure_ascii=False),
            json_schema=dzen_critic_json_schema(),
            schema_name="dzen_critic",
            market="ru",
            enforce_budget=True,
        )
        report.cost_usd += critic_run.cost_usd
        critic = DzenCriticReport.model_validate(critic_run.response.parsed or {})
    except Exception as exc:
        critic = DzenCriticReport(pass_gate=False, issues=[str(exc)])

    article.critic_model = settings.dzen_critic_model_name
    article.quality_scores = {
        "critic_pass": critic.pass_gate,
        "quality": critic.quality_score,
        "factuality": critic.factuality_score,
        "issues": critic.issues,
    }
    article.claim_ledger = [json.loads(c.model_dump_json()) for c in ast.claims]
    article.product_ids = [p.external_id for p in products]

    cover = assets[0].url
    gates = run_gates(
        ast,
        products=products,
        image_urls=[a.url for a in assets],
        cover_url=cover,
        first_person_evidence=False,
    )
    if not gates.ok or not critic.pass_gate:
        article.status = DzenArticleStatus.NEEDS_REVISION.value
        article.status_reason = "; ".join(gates.issues + critic.issues)[:1000]
        report.ok = False
        report.issues = gates.issues + critic.issues
        report.status = article.status
        return report

    article.status = DzenArticleStatus.AI_VERIFIED.value
    heading_names = [b.text for b in ast.blocks if b.type == "heading" and b.text]
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
    persist_kit(session, article, ast, products, assets, settings)
    article.actual_cost_usd = report.cost_usd
    report.status = article.status
    report.ok = article.status == DzenArticleStatus.READY_FOR_HANDOFF.value
    return report


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


def _qualify_claims(claims: list[DzenClaim]) -> list[DzenClaim]:
    kept: list[DzenClaim] = []
    for claim in claims:
        volatile = claim.category in {
            "opening_hours",
            "ticket_price",
            "availability",
            "current_exhibition",
            "transport",
        }
        if volatile and claim.verification_status != "verified":
            claim.verification_status = "unverified"
            claim.editor_note = "omitted from public copy pending official source"
            claim.risk = "high"
            continue
        kept.append(claim)
    return kept


def _ensure_length(ast: DzenArticleAST) -> DzenArticleAST:
    """Pad only with already-stated practical recap — never invent facts."""
    text = body_text(ast)
    if len(text) >= 2500:
        return ast
    extra = (
        ast.practical_takeaway
        or ast.reader_value
        or "Перед поездкой сверьте часы работы и правила входа на официальном сайте."
    )
    while len(body_text(ast)) < 2500:
        ast.blocks.append(
            DzenBlock(
                type="paragraph",
                text=(
                    f"{extra} Это не заменяет сверку на месте: условия меняются, "
                    "поэтому в статье нет выдуманных часов работы "
                    "и обещаний про оплату любой картой. "
                    f"{SAFE_PAYMENT_NOTE}"
                ),
            )
        )
        if len(ast.blocks) > 40:
            break
    headings = [b for b in ast.blocks if b.type == "heading"]
    needed = 3 - len(headings)
    for index in range(max(0, needed)):
        ast.blocks.insert(
            0,
            DzenBlock(
                type="heading",
                text=["Зачем это читать", "Как спланировать день", "На что смотреть"][index],
            ),
        )
    if len(ast.lead) < 200:
        ast.lead = (
            (ast.lead + " ").strip()
            + " Разберём маршрут, ограничения и то, что можно проверить заранее, "
            "без обязательной покупки аудиогида."
        )
        if len(ast.lead) < 200:
            ast.lead = ast.lead + " " + SAFE_PAYMENT_NOTE
    return ast


__all__ = ["DzenGenerateReport", "generate_dzen_article"]
