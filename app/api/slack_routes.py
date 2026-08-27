"""Slack endpoints: interactive buttons and the slash command.

Both verify the Slack signature before touching the database. Slack expects a reply
within three seconds, so the work is done inline and kept small.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.base import get_db
from app.errors import EngineError
from app.logging_setup import get_logger
from app.slack.commands import CommandHandler
from app.slack.interactions import InteractionHandler, verify_signature

log = get_logger("api.slack")

router = APIRouter(prefix="/slack", tags=["slack"])


async def _verified_body(request: Request, settings: Settings) -> bytes:
    if not settings.slack_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slack integration is disabled")
    if not settings.slack_signing_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "SLACK_SIGNING_SECRET is not configured"
        )

    body = await request.body()
    ok = verify_signature(
        signing_secret=settings.slack_signing_secret,
        timestamp=request.headers.get("X-Slack-Request-Timestamp", ""),
        body=body,
        signature=request.headers.get("X-Slack-Signature", ""),
    )
    if not ok:
        log.warning("slack.bad_signature", path=request.url.path)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid Slack signature")
    return body


@router.post("/interactions")
async def interactions(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    await _verified_body(request, settings)
    form = await request.form()
    raw = form.get("payload")
    if not isinstance(raw, str):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing payload")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed payload") from exc

    handler = InteractionHandler(session, settings)
    try:
        result = handler.handle(payload)
    except EngineError as exc:
        log.warning("slack.action_failed", error=str(exc))
        return {
            "response_type": "ephemeral",
            "text": f"Не получилось: {exc}",
        }
    return result.as_response()


@router.post("/commands")
async def commands(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    await _verified_body(request, settings)
    form = await request.form()
    text = form.get("text")
    return CommandHandler(session, settings).handle(text if isinstance(text, str) else "")


__all__ = ["router"]
