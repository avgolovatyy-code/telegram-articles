"""Public (tokenized) Publishing Kit pages and Slack event capture."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.base import get_db
from app.db.models import DzenArticle, DzenHandoffBatch, DzenHandoffItem, DzenPublishingKit
from app.dzen.confirm import parse_thread_reply, verify_and_confirm
from app.dzen.kit import kit_is_expired
from app.logging_setup import get_logger

log = get_logger("dzen.routes")

router = APIRouter(tags=["dzen"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "admin" / "templates")
)


def _kit_by_token(session: Session, token: str) -> tuple[DzenPublishingKit, DzenArticle]:
    kit = session.scalar(select(DzenPublishingKit).where(DzenPublishingKit.access_token == token))
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kit not found")
    article = session.get(DzenArticle, kit.article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    if kit_is_expired(kit):
        raise HTTPException(status.HTTP_410_GONE, "publishing kit expired")
    return kit, article


def kit_context(
    request: Request,
    kit: DzenPublishingKit,
    article: DzenArticle,
    settings: Settings,
    *,
    admin: bool = False,
) -> dict:
    preview = (article.quality_scores or {}).get("preview_html") or kit.html_body
    return {
        "request": request,
        "active": "dzen",
        "kit": kit,
        "article": article,
        "preview_html": preview,
        "products": kit.product_links_json or [],
        "media": kit.media_manifest_json or [],
        "stale": kit.stale,
        "studio_url": settings.dzen_studio_url,
        "admin": admin,
        "referer_id": settings.wegotrip_referer_id,
        "clipboard_enabled": settings.dzen_render_rich_clipboard,
        "budget": type("B", (), {"spent_usd": 0, "budget_usd": 0})(),
        "messages": [],
        "channels": {
            "en": settings.telegram_en_channel,
            "ru": settings.telegram_ru_channel,
            "test": settings.telegram_test_channel,
        },
    }


@router.get("/dzen/k/{token}", response_class=HTMLResponse)
def public_kit(
    token: str,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    kit, article = _kit_by_token(session, token)
    ctx = kit_context(request, kit, article, settings)
    flash = request.query_params.get("msg")
    if flash:
        ctx["messages"] = [(request.query_params.get("level", "ok"), flash)]
    return templates.TemplateResponse(request, "dzen_kit.html", ctx)


@router.get("/dzen/k/{token}/article.html")
def public_kit_html(token: str, session: Session = Depends(get_db)) -> HTMLResponse:
    kit, _article = _kit_by_token(session, token)
    return HTMLResponse(kit.html_body)


@router.get("/dzen/k/{token}/article.txt")
def public_kit_txt(token: str, session: Session = Depends(get_db)) -> PlainTextResponse:
    kit, _article = _kit_by_token(session, token)
    return PlainTextResponse(kit.plain_body)


@router.get("/dzen/k/{token}/media.zip")
def public_kit_zip(token: str, session: Session = Depends(get_db)) -> FileResponse:
    kit, _article = _kit_by_token(session, token)
    if not kit.zip_asset_path or not Path(kit.zip_asset_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "zip not ready")
    return FileResponse(
        kit.zip_asset_path,
        media_type="application/zip",
        filename="dzen_media.zip",
    )


@router.post("/dzen/k/{token}/confirm")
def public_kit_confirm(
    token: str,
    published_url: str = Form(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    _kit, article = _kit_by_token(session, token)
    result = verify_and_confirm(
        session,
        article,
        published_url,
        confirmed_by="kit_form",
        network=settings.validate_media_over_network,
    )
    level = "ok" if result.ok else "error"
    msg = "Публикация подтверждена" if result.ok else (result.reason or "не подтверждено")
    return RedirectResponse(
        f"/dzen/k/{token}?{urlencode({'msg': msg, 'level': level})}",
        status_code=303,
    )


@router.post("/slack/events")
async def slack_events(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Capture thread replies with dzen.ru URLs. url_verification handshake included."""
    payload = await request.json()
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    if not settings.dzen_slack_thread_reply_capture:
        return {"ok": True, "skipped": "capture_disabled"}
    event = payload.get("event") or {}
    if event.get("type") != "message" or event.get("subtype"):
        return {"ok": True}
    thread_ts = event.get("thread_ts")
    text = event.get("text") or ""
    if not thread_ts:
        return {"ok": True}
    batch = session.scalar(
        select(DzenHandoffBatch).where(DzenHandoffBatch.slack_thread_ts == thread_ts)
    )
    if batch is None:
        return {"ok": True}
    mapping = parse_thread_reply(text, batch.item_count)
    items = list(
        session.scalars(
            select(DzenHandoffItem)
            .where(DzenHandoffItem.batch_id == batch.id)
            .order_by(DzenHandoffItem.position)
        )
    )
    for position, url in mapping.items():
        if position < 1 or position > len(items):
            continue
        item = items[position - 1]
        article = session.get(DzenArticle, item.article_id)
        if article is None:
            continue
        verify_and_confirm(
            session,
            article,
            url,
            confirmed_by=f"slack:{event.get('user', 'thread')}",
            network=settings.validate_media_over_network,
        )
    if not mapping and batch.item_count > 1 and "dzen.ru" in text:
        log.info("dzen.thread.ambiguous", batch_id=batch.id)
    return {"ok": True}


__all__ = ["kit_context", "router"]
