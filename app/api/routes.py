"""Public HTTP endpoints: click tracking, health and read-only JSON stats."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.budget import BudgetManager
from app.analytics.reports import AnalyticsService
from app.analytics.tracking import TrackingService, visitor_fingerprint
from app.config import get_settings
from app.db.base import get_db

router = APIRouter()


@router.get("/r/{token}", include_in_schema=False)
def redirect(token: str, request: Request, session: Session = Depends(get_db)) -> RedirectResponse:
    """Count the click and forward to the affiliate URL."""
    tracking = TrackingService(session)
    link = tracking.resolve(token)
    if link is None:
        settings = get_settings()
        return RedirectResponse(f"https://{settings.wegotrip_store_domain_en}/", status_code=302)

    client_host = request.client.host if request.client else None
    tracking.record_click(
        link,
        visitor_hash=visitor_fingerprint(client_host, request.headers.get("user-agent")),
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )
    return RedirectResponse(link.target_url, status_code=302)


@router.get("/api/stats", tags=["ops"])
def stats(session: Session = Depends(get_db)) -> dict[str, Any]:
    analytics = AnalyticsService(session)
    budget = BudgetManager(session)
    snapshot = budget.snapshot()
    return {
        "budget": {
            "date": snapshot.spend_date.isoformat(),
            "budget_usd": snapshot.budget_usd,
            "spent_usd": snapshot.spent_usd,
            "reserved_usd": snapshot.reserved_usd,
            "remaining_usd": snapshot.remaining_usd,
            "generated": snapshot.generated,
            "average_article_cost_usd": snapshot.average_article_cost_usd,
        },
        "markets": [overview.as_dict() for overview in analytics.overviews()],
        "kpis": analytics.kpis(),
    }


@router.get("/readyz", tags=["ops"])
def readyz(session: Session = Depends(get_db)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


__all__ = ["router"]
