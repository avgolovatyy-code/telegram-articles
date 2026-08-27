"""Catalogue coverage and topic exhaustion.

The daily article counts are a *ceiling*, not an obligation. When the catalogue has
no more entity × intent combinations that clear the quality bar, the engine stops and
says so. It never lowers `MIN_TOPIC_SCORE`, never relaxes `min_inventory` and never
re-uses an entity with a thinner intent just to hit a quota — that is exactly the
"выдумывать темы" failure mode.

New material appears on its own: `sync_catalog` picks up new products, cities and
attractions, and the next `discover_topics` run turns them into candidates.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Market, Settings, get_settings
from app.db.enums import TopicStatus
from app.db.models import Product, TopicCandidate
from app.db.types import utcnow


@dataclass(slots=True)
class CoverageReport:
    market: str
    #: Candidates that are still unused and clear ``MIN_TOPIC_SCORE``.
    usable_candidates: int
    #: Unused candidates that exist but score too low to be worth writing.
    below_threshold: int
    used_topics: int
    duplicate_topics: int
    rejected_topics: int
    available_products: int
    new_products_7d: int
    last_new_product_at: dt.datetime | None
    exhausted: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["last_new_product_at"] = (
            self.last_new_product_at.isoformat() if self.last_new_product_at else None
        )
        return data

    @property
    def coverage_ratio(self) -> float:
        total = self.used_topics + self.usable_candidates
        return round(self.used_topics / total, 4) if total else 0.0


def usable_candidate_query(market: Market, settings: Settings):
    """Candidates worth generating: unused and above the quality floor."""
    return select(TopicCandidate).where(
        TopicCandidate.market == market,
        TopicCandidate.status == TopicStatus.CANDIDATE,
        (TopicCandidate.topic_score + TopicCandidate.boost) >= settings.min_topic_score,
    )


def assess_coverage(
    session: Session, market: Market, settings: Settings | None = None
) -> CoverageReport:
    settings = settings or get_settings()

    def count_topics(*conditions: Any) -> int:
        return int(
            session.scalar(
                select(func.count(TopicCandidate.id)).where(
                    TopicCandidate.market == market, *conditions
                )
            )
            or 0
        )

    usable = int(
        session.scalar(
            select(func.count()).select_from(usable_candidate_query(market, settings).subquery())
        )
        or 0
    )
    below = count_topics(
        TopicCandidate.status == TopicStatus.CANDIDATE,
        (TopicCandidate.topic_score + TopicCandidate.boost) < settings.min_topic_score,
    )
    used = count_topics(TopicCandidate.status == TopicStatus.USED)
    duplicates = count_topics(TopicCandidate.status == TopicStatus.DUPLICATE)
    rejected = count_topics(TopicCandidate.status == TopicStatus.REJECTED)

    products = int(
        session.scalar(
            select(func.count(Product.id)).where(
                Product.market == market, Product.available.is_(True)
            )
        )
        or 0
    )
    week_ago = utcnow() - dt.timedelta(days=7)
    new_products = int(
        session.scalar(
            select(func.count(Product.id)).where(
                Product.market == market, Product.created_at >= week_ago
            )
        )
        or 0
    )
    last_new = session.scalar(select(func.max(Product.created_at)).where(Product.market == market))

    if usable > 0:
        exhausted = False
        reason = f"{usable} candidate topics above the quality floor"
    elif below > 0:
        exhausted = True
        reason = (
            f"no topic clears MIN_TOPIC_SCORE={settings.min_topic_score}; "
            f"{below} weak candidates were deliberately left unwritten"
        )
    elif products == 0:
        exhausted = True
        reason = "the catalogue is empty for this market — run sync_catalog"
    else:
        exhausted = True
        reason = (
            "every entity × intent combination in the catalogue is already covered; "
            "new topics appear when the Affiliate API returns new material"
        )

    return CoverageReport(
        market=market,
        usable_candidates=usable,
        below_threshold=below,
        used_topics=used,
        duplicate_topics=duplicates,
        rejected_topics=rejected,
        available_products=products,
        new_products_7d=new_products,
        last_new_product_at=last_new,
        exhausted=exhausted,
        reason=reason,
    )


__all__ = ["CoverageReport", "assess_coverage", "usable_candidate_query"]
