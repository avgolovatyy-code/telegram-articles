"""Rolling 30-day Dzen portfolio: genre mix, geography, commercial density."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DzenArticleStatus
from app.db.models import DzenArticle
from app.db.types import utcnow
from app.dzen.genre import genre_from_format


def portfolio_report(session: Session, *, now: dt.datetime | None = None) -> dict[str, Any]:
    clock = now or utcnow()
    start = (clock - dt.timedelta(days=30)).date()
    rows = list(
        session.scalars(
            select(DzenArticle).where(
                DzenArticle.planned_date >= start,
                DzenArticle.status.notin_(
                    [DzenArticleStatus.CANCELLED.value, DzenArticleStatus.BLOCKED.value]
                ),
            )
        )
    )
    genres: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    first_pass = 0
    holds = 0
    with_products = 0
    cost_usd = 0.0
    for article in rows:
        brief = article.brief if isinstance(article.brief, dict) else {}
        genre = brief.get("genre") or genre_from_format(article.format)
        genres[genre] += 1
        if article.destination_country:
            countries[article.destination_country] += 1
        scores = article.quality_scores or {}
        if scores.get("editorial_decision") == "accept" and not scores.get("rewritten"):
            first_pass += 1
        if article.status == DzenArticleStatus.NEEDS_REVISION.value:
            holds += 1
        if article.product_ids:
            with_products += 1
        if article.status_reason:
            reasons[article.status_reason[:80]] += 1
        cost_usd += float(article.actual_cost_usd or 0)
    heavy_genre = genres.most_common(1)[0][0] if genres else ""
    return {
        "window_days": 30,
        "article_count": len(rows),
        "genres": dict(genres),
        "countries": dict(countries),
        "first_pass_accept": first_pass,
        "holds": holds,
        "with_products": with_products,
        "zero_product_share": (len(rows) - with_products) / len(rows) if rows else 0.0,
        "cost_usd": round(cost_usd, 4),
        "hold_reasons": dict(reasons),
        "heavy_genre": heavy_genre,
    }


__all__ = ["portfolio_report"]
