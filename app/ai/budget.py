"""AI Budget Manager.

Enforces the hard cap ``DAILY_AI_BUDGET_USD`` (default $3.00/day) across LLM calls,
web-search tool calls and generated images.

Rules implemented (spec §13):

1. Serve the per-market minimums first (10 EN + 10 RU), then grow towards the maxima.
2. Use a rolling average cost per article to project spend.
3. Refuse to start a generation job whose projected cost exceeds the remaining budget.
4. Never exceed the hard cap automatically.
5. Publishing an already-generated article is never blocked by the budget.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.pricing import estimate_cost
from app.config import MARKETS, Market, Settings, get_settings
from app.db.enums import CostKind
from app.db.models import Article, BudgetReservation, CostLedgerEntry, LLMRun
from app.db.types import utcnow
from app.errors import BudgetExceeded
from app.logging_setup import get_logger

log = get_logger("ai.budget")

RESERVATION_HELD = "held"
RESERVATION_SETTLED = "settled"
RESERVATION_RELEASED = "released"

#: Reservations older than this are considered abandoned (crashed worker) and freed.
RESERVATION_TTL = dt.timedelta(minutes=45)


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    spend_date: dt.date
    budget_usd: float
    spent_usd: float
    reserved_usd: float
    generated: dict[str, int]
    average_article_cost_usd: float

    @property
    def committed_usd(self) -> float:
        return round(self.spent_usd + self.reserved_usd, 6)

    @property
    def remaining_usd(self) -> float:
        return round(max(0.0, self.budget_usd - self.committed_usd), 6)


@dataclass(frozen=True, slots=True)
class GenerationDecision:
    allowed: bool
    reason: str
    projected_cost_usd: float
    remaining_usd: float


class BudgetManager:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------ state
    @staticmethod
    def today() -> dt.date:
        return utcnow().date()

    def spent(self, day: dt.date | None = None) -> float:
        day = day or self.today()
        total = self.session.scalar(
            select(func.coalesce(func.sum(CostLedgerEntry.amount_usd), 0.0)).where(
                CostLedgerEntry.spend_date == day
            )
        )
        return float(total or 0.0)

    def reserved(self, day: dt.date | None = None) -> float:
        day = day or self.today()
        self.expire_stale_reservations()
        total = self.session.scalar(
            select(func.coalesce(func.sum(BudgetReservation.amount_usd), 0.0)).where(
                BudgetReservation.spend_date == day,
                BudgetReservation.status == RESERVATION_HELD,
            )
        )
        return float(total or 0.0)

    def generated_counts(self, day: dt.date | None = None) -> dict[str, int]:
        day = day or self.today()
        start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
        end = start + dt.timedelta(days=1)
        counts: dict[str, int] = {}
        for market in MARKETS:
            counts[market] = int(
                self.session.scalar(
                    select(func.count(Article.id)).where(
                        Article.market == market,
                        Article.created_at >= start,
                        Article.created_at < end,
                        Article.generation_attempts > 0,
                    )
                )
                or 0
            )
        return counts

    def average_article_cost(self, *, lookback_days: int = 7) -> float:
        """Rolling average actual cost per generated article."""
        since = utcnow() - dt.timedelta(days=lookback_days)
        row = self.session.execute(
            select(
                func.coalesce(func.sum(Article.actual_cost_usd), 0.0),
                func.count(Article.id),
            ).where(Article.created_at >= since, Article.actual_cost_usd > 0)
        ).one()
        total, count = float(row[0] or 0.0), int(row[1] or 0)
        if count == 0:
            return self.settings.default_estimated_article_cost_usd
        return round(total / count, 6)

    def snapshot(self, day: dt.date | None = None) -> BudgetSnapshot:
        day = day or self.today()
        return BudgetSnapshot(
            spend_date=day,
            budget_usd=self.settings.daily_ai_budget_usd,
            spent_usd=round(self.spent(day), 6),
            reserved_usd=round(self.reserved(day), 6),
            generated=self.generated_counts(day),
            average_article_cost_usd=self.average_article_cost(),
        )

    # ------------------------------------------------------------- decisions
    def plan_daily_generation(self, day: dt.date | None = None) -> dict[str, int]:
        """How many more articles to generate per market today.

        Minimums for every market are funded first; only then is the leftover budget
        used to grow towards the maxima, alternating between markets.
        """
        snapshot = self.snapshot(day)
        avg = max(snapshot.average_article_cost_usd, 1e-6)
        budget_left = max(0.0, snapshot.remaining_usd - self.settings.budget_safety_margin_usd)
        affordable = int(budget_left // avg)

        plan: dict[str, int] = dict.fromkeys(MARKETS, 0)

        def fill(ceiling_for: Callable[[Market], int]) -> None:
            """Hand out one article at a time so neither market starves."""
            nonlocal affordable
            while affordable > 0:
                progressed = False
                for market in MARKETS:
                    if affordable <= 0:
                        break
                    if snapshot.generated[market] + plan[market] >= ceiling_for(market):
                        continue
                    plan[market] += 1
                    affordable -= 1
                    progressed = True
                if not progressed:
                    return

        # Phase 1 — both minimums, alternating between markets.
        fill(self.settings.articles_min_per_day)
        # Phase 2 — grow towards the maxima with whatever budget is left.
        fill(self.settings.articles_max_per_day)
        return plan

    def can_start_article(
        self, market: Market, *, estimated_cost_usd: float | None = None
    ) -> GenerationDecision:
        snapshot = self.snapshot()
        projected = (
            estimated_cost_usd
            if estimated_cost_usd is not None
            else snapshot.average_article_cost_usd
        )
        remaining = snapshot.remaining_usd - self.settings.budget_safety_margin_usd

        if snapshot.generated[market] >= self.settings.articles_max_per_day(market):
            return GenerationDecision(
                False, f"daily maximum for {market} reached", projected, snapshot.remaining_usd
            )
        if projected > remaining:
            return GenerationDecision(
                False,
                f"projected ${projected:.4f} exceeds remaining ${max(remaining, 0):.4f}",
                projected,
                snapshot.remaining_usd,
            )
        below_min = snapshot.generated[market] < self.settings.articles_min_per_day(market)
        reason = "within daily minimum" if below_min else "within daily budget"
        return GenerationDecision(True, reason, projected, snapshot.remaining_usd)

    # ----------------------------------------------------------- reservations
    def reserve(
        self,
        market: Market,
        amount_usd: float,
        *,
        article_id: int | None = None,
        job_id: str | None = None,
    ) -> BudgetReservation:
        decision = self.can_start_article(market, estimated_cost_usd=amount_usd)
        if not decision.allowed:
            raise BudgetExceeded(
                decision.reason,
                remaining_usd=decision.remaining_usd,
                projected_usd=decision.projected_cost_usd,
            )
        reservation = BudgetReservation(
            spend_date=self.today(),
            market=market,
            article_id=article_id,
            amount_usd=amount_usd,
            status=RESERVATION_HELD,
            job_id=job_id,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def settle(self, reservation: BudgetReservation) -> None:
        reservation.status = RESERVATION_SETTLED
        reservation.released_at = utcnow()
        self.session.flush()

    def release(self, reservation: BudgetReservation) -> None:
        reservation.status = RESERVATION_RELEASED
        reservation.released_at = utcnow()
        self.session.flush()

    def expire_stale_reservations(self) -> int:
        cutoff = utcnow() - RESERVATION_TTL
        stale = self.session.scalars(
            select(BudgetReservation).where(
                BudgetReservation.status == RESERVATION_HELD,
                BudgetReservation.created_at < cutoff,
            )
        ).all()
        for reservation in stale:
            reservation.status = RESERVATION_RELEASED
            reservation.released_at = utcnow()
            log.warning("budget.reservation_expired", reservation_id=reservation.id)
        if stale:
            self.session.flush()
        return len(stale)

    # ---------------------------------------------------------------- ledger
    def record(
        self,
        *,
        amount_usd: float,
        market: Market | None = None,
        article_id: int | None = None,
        llm_run_id: int | None = None,
        kind: CostKind | str = CostKind.LLM,
        task: str | None = None,
        model: str | None = None,
        note: str | None = None,
    ) -> CostLedgerEntry:
        entry = CostLedgerEntry(
            spend_date=self.today(),
            market=market,
            article_id=article_id,
            llm_run_id=llm_run_id,
            kind=str(kind),
            task=task,
            model=model,
            amount_usd=round(amount_usd, 6),
            note=note,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def hard_cap_reached(self) -> bool:
        return self.spent() >= self.settings.daily_ai_budget_usd

    # ------------------------------------------------------------ estimation
    def estimate_article_cost(
        self,
        *,
        writer_model: str,
        review_model: str,
        context_chars: int,
        expected_output_chars: int,
        web_search_calls: int = 0,
        generated_images: int = 0,
    ) -> float:
        context_tokens = max(1, context_chars // 4)
        output_tokens = max(1, expected_output_chars // 4)
        writer = estimate_cost(
            writer_model,
            input_tokens=context_tokens,
            output_tokens=output_tokens,
            web_search_calls=web_search_calls,
            generated_images=generated_images,
        )
        review = estimate_cost(
            review_model,
            input_tokens=context_tokens // 2 + output_tokens,
            output_tokens=400,
        )
        return round(writer + review, 6)

    def today_llm_runs(self) -> list[LLMRun]:
        start = dt.datetime.combine(self.today(), dt.time.min, tzinfo=dt.UTC)
        return list(self.session.scalars(select(LLMRun).where(LLMRun.created_at >= start)).all())


__all__ = [
    "RESERVATION_HELD",
    "RESERVATION_RELEASED",
    "RESERVATION_SETTLED",
    "BudgetManager",
    "BudgetSnapshot",
    "GenerationDecision",
]
