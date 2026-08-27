"""Admin UI.

Server-rendered Jinja templates: no build step, no SPA. Optional HTTP basic auth via
``ADMIN_USERNAME`` / ``ADMIN_PASSWORD``.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin.preview import render_preview
from app.ai.budget import BudgetManager
from app.analytics.reports import AnalyticsService
from app.config import Settings, get_settings
from app.db.base import get_db
from app.db.enums import ArticleStatus, EntityType, TopicStatus
from app.db.models import Article, PublicationQueueItem, TopicCandidate
from app.errors import EngineError
from app.generation.schemas import ArticleDocument
from app.logging_setup import get_logger
from app.scheduler import jobs
from app.services.rendering import render_stored_article
from app.services.workflow import ArticleWorkflow
from app.telegram.blocks import collect_urls, message_stats, validate_rich_message

log = get_logger("admin")

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(
    directory=str(__import__("pathlib").Path(__file__).parent / "templates")
)
security = HTTPBasic(auto_error=False)

_OK_STATUSES = {"published", "approved", "ok", "verified", "used"}
_WARN_STATUSES = {
    "needs_review",
    "draft",
    "scheduled",
    "pending",
    "in_progress",
    "generating",
    "researching",
    "candidate",
    "queued",
}
_ERR_STATUSES = {
    "failed",
    "validation_failed",
    "rejected",
    "duplicate",
    "unverified",
    "omitted",
    "cancelled",
}


def status_class(value: str) -> str:
    value = str(value)
    if value in _OK_STATUSES:
        return "ok"
    if value in _WARN_STATUSES:
        return "warn"
    if value in _ERR_STATUSES:
        return "err"
    return ""


def claim_class(value: str) -> str:
    return status_class(value)


templates.env.globals["status_class"] = status_class
templates.env.globals["claim_class"] = claim_class


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> str:
    if not settings.admin_password:
        return "local"
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    password_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (user_ok and password_ok):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _base_context(
    request: Request, session: Session, settings: Settings, active: str
) -> dict[str, Any]:
    snapshot = BudgetManager(session, settings).snapshot()
    messages = []
    flash = request.query_params.get("msg")
    level = request.query_params.get("level", "ok")
    if flash:
        messages.append((level, flash))
    return {
        "request": request,
        "active": active,
        "budget": snapshot,
        "messages": messages,
        "referer_id": settings.wegotrip_referer_id,
        "channels": {
            "en": settings.telegram_en_channel,
            "ru": settings.telegram_ru_channel,
            "test": settings.telegram_test_channel,
        },
    }


def _redirect(path: str, message: str, level: str = "ok") -> RedirectResponse:
    return RedirectResponse(
        f"{path}?{urlencode({'msg': message, 'level': level})}", status_code=303
    )


# ------------------------------------------------------------------ dashboard
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    analytics = AnalyticsService(session, settings)
    budget = BudgetManager(session, settings)
    context = _base_context(request, session, settings, "dashboard")
    context |= {
        "overviews": analytics.overviews(),
        "plan": budget.plan_daily_generation(),
        "auto_publish": {"en": settings.auto_publish_en, "ru": settings.auto_publish_ru},
        "recent_articles": list(
            session.scalars(select(Article).order_by(Article.created_at.desc()).limit(15)).all()
        ),
        "top_topics": list(
            session.scalars(
                select(TopicCandidate)
                .where(TopicCandidate.status == TopicStatus.CANDIDATE)
                .order_by((TopicCandidate.topic_score + TopicCandidate.boost).desc())
                .limit(15)
            ).all()
        ),
    }
    return templates.TemplateResponse(request, "dashboard.html", context)


# ---------------------------------------------------------------------- topics
@router.get("/topics", response_class=HTMLResponse)
def topics_page(
    request: Request,
    market: str | None = Query(None),
    topic_status: str | None = Query(None, alias="status"),
    entity_type: str | None = Query(None),
    q: str | None = Query(None),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    query = select(TopicCandidate)
    if market:
        query = query.where(TopicCandidate.market == market)
    if topic_status:
        query = query.where(TopicCandidate.status == topic_status)
    if entity_type:
        query = query.where(TopicCandidate.entity_type == entity_type)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                TopicCandidate.primary_query.ilike(pattern),
                TopicCandidate.entity_name.ilike(pattern),
            )
        )

    total = len(list(session.scalars(query).all()))
    rows = list(
        session.scalars(
            query.order_by((TopicCandidate.topic_score + TopicCandidate.boost).desc())
            .offset(offset)
            .limit(100)
        ).all()
    )

    context = _base_context(request, session, settings, "topics")
    context |= {
        "topics": rows,
        "total": total,
        "statuses": [s.value for s in TopicStatus],
        "entity_types": [e.value for e in EntityType],
        "filters": {"market": market, "status": topic_status, "entity_type": entity_type, "q": q},
        "next_query": urlencode(
            {
                k: v
                for k, v in {
                    "market": market,
                    "status": topic_status,
                    "entity_type": entity_type,
                    "q": q,
                    "offset": offset + 100,
                }.items()
                if v
            }
        ),
    }
    return templates.TemplateResponse(request, "topics.html", context)


@router.post("/topics/{topic_id}/action")
def topic_action(
    topic_id: int,
    action: str = Form(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> RedirectResponse:
    topic = session.get(TopicCandidate, topic_id)
    if topic is None:
        raise HTTPException(404, "topic not found")

    match action:
        case "boost":
            topic.boost = round(min(0.5, topic.boost + 0.1), 3)
            message = f"boosted to +{topic.boost}"
        case "ignore":
            topic.status = TopicStatus.IGNORED
            message = "topic ignored"
        case "exclude":
            topic.status = TopicStatus.REJECTED
            topic.status_reason = "excluded by an editor"
            message = "topic excluded"
        case "generate":
            from app.ai.router import LLMGateway
            from app.generation.pipeline import GenerationPipeline

            gateway = LLMGateway(session, settings=settings)
            pipeline = GenerationPipeline(session, gateway, settings=settings)
            try:
                outcome = pipeline.generate(topic)
            except EngineError as exc:
                return _redirect("/admin/topics", f"generation failed: {exc}", "error")
            if outcome.article is None:
                return _redirect("/admin/topics", f"skipped: {outcome.reason}", "error")
            return _redirect(
                f"/admin/articles/{outcome.article.id}", f"generated ({outcome.status})"
            )
        case _:
            raise HTTPException(400, f"unknown action {action}")

    session.flush()
    return _redirect("/admin/topics", message)


# -------------------------------------------------------------------- articles
@router.get("/articles", response_class=HTMLResponse)
def articles_page(
    request: Request,
    market: str | None = Query(None),
    article_status: str | None = Query(None, alias="status"),
    q: str | None = Query(None),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    query = select(Article)
    if market:
        query = query.where(Article.market == market)
    if article_status:
        query = query.where(Article.status == article_status)
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(Article.title.ilike(pattern), Article.primary_query.ilike(pattern)))

    context = _base_context(request, session, settings, "articles")
    context |= {
        "articles": list(
            session.scalars(query.order_by(Article.created_at.desc()).limit(200)).all()
        ),
        "statuses": [s.value for s in ArticleStatus],
        "filters": {"market": market, "status": article_status, "q": q},
    }
    return templates.TemplateResponse(request, "articles.html", context)


@router.get("/articles/{article_id}", response_class=HTMLResponse)
def article_detail(
    request: Request,
    article_id: int,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "article not found")
    context = _base_context(request, session, settings, "articles")
    context |= {"article": article, "preview": render_preview(article.rendered_message)}
    return templates.TemplateResponse(request, "article_detail.html", context)


@router.get("/articles/{article_id}/payload", response_class=HTMLResponse)
def article_payload(
    request: Request,
    article_id: int,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "article not found")
    message = article.rendered_message or {}
    context = _base_context(request, session, settings, "articles")
    context |= {
        "article": article,
        "payload_json": json.dumps(message, ensure_ascii=False, indent=2),
        "stats": message_stats(message),
        "errors": validate_rich_message(message) if message else ["nothing rendered"],
        "urls": collect_urls(message),
    }
    return templates.TemplateResponse(request, "payload.html", context)


@router.get("/articles/{article_id}/edit", response_class=HTMLResponse)
def article_edit_form(
    request: Request,
    article_id: int,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "article not found")
    context = _base_context(request, session, settings, "articles")
    context |= {
        "article": article,
        "body_json": json.dumps(article.body or {}, ensure_ascii=False, indent=2),
    }
    return templates.TemplateResponse(request, "article_edit.html", context)


@router.post("/articles/{article_id}/edit")
def article_edit(
    article_id: int,
    body: str = Form(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> RedirectResponse:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "article not found")
    try:
        document = ArticleDocument.model_validate(json.loads(body))
    except (json.JSONDecodeError, ValueError) as exc:
        return _redirect(f"/admin/articles/{article_id}/edit", f"invalid JSON: {exc}", "error")

    article.body = document.model_dump()
    article.title = document.title
    article.char_count = document.char_count()
    article.current_version += 1
    rendered = render_stored_article(session, article, settings=settings)
    article.rendered_message = rendered.message
    session.flush()
    return _redirect(f"/admin/articles/{article_id}", "article updated and re-rendered")


@router.post("/articles/{article_id}/action")
def article_action(
    article_id: int,
    action: str = Form(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin: str = Depends(require_admin),
) -> RedirectResponse:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "article not found")
    workflow = ArticleWorkflow(session, settings)
    target = f"/admin/articles/{article_id}"

    try:
        match action:
            case "approve":
                result = workflow.approve(article, by=admin)
            case "reject":
                result = workflow.reject(article, reason="rejected by an editor", by=admin)
            case "publish_test":
                result = workflow.publish_test(article)
            case "publish":
                result = workflow.publish_now(article)
            case "regenerate":
                outcome = workflow.regenerate(article)
                if outcome.article is None:
                    return _redirect(target, f"regeneration skipped: {outcome.reason}", "error")
                return _redirect(
                    f"/admin/articles/{outcome.article.id}", f"regenerated ({outcome.status})"
                )
            case "verify":
                stale = jobs.refresh_article_products(session, article, settings=settings)
                rendered = render_stored_article(session, article, settings=settings)
                article.rendered_message = rendered.message
                session.flush()
                note = (
                    f"products refreshed, {len(stale)} unavailable"
                    if stale
                    else "products refreshed"
                )
                return _redirect(target, note)
            case _:
                raise HTTPException(400, f"unknown action {action}")
    except EngineError as exc:
        return _redirect(target, str(exc), "error")

    return _redirect(target, result.message, "ok" if result.ok else "error")


@router.post("/articles/{article_id}/schedule")
def article_schedule(
    article_id: int,
    when: str = Form(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> RedirectResponse:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "article not found")
    try:
        moment = dt.datetime.fromisoformat(when)
    except ValueError:
        return _redirect(f"/admin/articles/{article_id}", "invalid date", "error")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    result = ArticleWorkflow(session, settings).schedule(article, moment)
    return _redirect(
        f"/admin/articles/{article_id}", result.message, "ok" if result.ok else "error"
    )


# ------------------------------------------------------------------- analytics
@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    analytics = AnalyticsService(session, settings)
    kpis = analytics.kpis()
    context = _base_context(request, session, settings, "analytics")
    context |= {
        "headline": [
            ("Articles published", kpis["articles_published"]),
            ("Clicks", kpis["clicks"]),
            ("Orders", kpis["orders"]),
            ("Revenue", f"{kpis['revenue']:.2f}"),
            ("AI cost total", f"${kpis['ai_cost_total_usd']:.2f}"),
            ("AI cost / article", f"${kpis['ai_cost_per_article']:.4f}"),
            ("Conversion rate", f"{kpis['conversion_rate'] * 100:.2f}%"),
            ("Revenue / article", f"{kpis['revenue_per_article']:.2f}"),
        ],
        "spend": analytics.spend_by_day(),
        "performance": analytics.article_performance(),
    }
    return templates.TemplateResponse(request, "analytics.html", context)


# -------------------------------------------------------------------------- ops
@router.get("/ops", response_class=HTMLResponse)
def ops_page(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> HTMLResponse:
    runner = getattr(request.app.state, "scheduler", None)
    context = _base_context(request, session, settings, "ops")
    context |= {
        "scheduler_jobs": runner.jobs_summary() if runner else [],
        "queue": list(
            session.scalars(
                select(PublicationQueueItem)
                .order_by(PublicationQueueItem.scheduled_for.desc())
                .limit(40)
            ).all()
        ),
        "config": {
            "writer_model": settings.openai_writer_model,
            "utility_model": settings.openai_utility_model,
            "fallback_model": settings.openai_fallback_model,
            "review_model": settings.review_model,
            "llm_provider": settings.llm_provider,
            "daily_budget": settings.daily_ai_budget_usd,
            "en_min": settings.en_articles_min_per_day,
            "en_max": settings.en_articles_max_per_day,
            "ru_min": settings.ru_articles_min_per_day,
            "ru_max": settings.ru_articles_max_per_day,
            "auto_en": settings.auto_publish_en,
            "auto_ru": settings.auto_publish_ru,
            "min_interval": settings.min_post_interval_minutes,
            "generated_covers": settings.allow_generated_covers,
            "hashtags": settings.enable_hashtags,
            "max_hashtags": settings.max_hashtags,
            "catalog_provider": settings.catalog_provider,
            "dry_run": settings.telegram_dry_run,
        },
    }
    return templates.TemplateResponse(request, "ops.html", context)


@router.post("/ops/run")
def ops_run(
    job: str = Form(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> RedirectResponse:
    handlers = {
        "seed": jobs.seed_reference_data,
        "sync_catalog": jobs.sync_catalog,
        "discover_topics": jobs.discover_topics,
        "generate": jobs.generate_daily_articles,
        "schedule": jobs.schedule_publications,
        "publish_queue": jobs.process_publication_queue,
        "cleanup": jobs.cleanup_expired,
    }
    handler = handlers.get(job)
    if handler is None:
        raise HTTPException(400, f"unknown job {job}")
    try:
        report = handler(session, settings=settings)
    except EngineError as exc:
        return _redirect("/admin/ops", f"{job} failed: {exc}", "error")
    summary = ", ".join(f"{k}={v}" for k, v in list(report.details.items())[:4])
    return _redirect("/admin/ops", f"{job}: {summary or 'done'}", "ok" if report.ok else "error")


__all__ = ["router"]
