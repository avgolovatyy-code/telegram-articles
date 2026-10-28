"""Max Russia editorial policy — topic eligibility, balance, calendar (§6.1).

Combines ``MaxRussiaAudienceGate``, ``RussianRegionCoveragePlanner`` and
Russian holiday context. Soft targets, not hard weekly quotas.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from app.max.audience import Benefit, MaxAudienceDecision, MaxRussiaAudienceGate
from app.max.holidays import RussiaCalendarContext, russia_calendar_context
from app.max.regions import RussianRegionCoveragePlanner, normalize_region_key
from app.topics.geo import TopicGeo

DomesticOrOutbound = Literal["domestic", "outbound"]


@dataclass(slots=True)
class MaxBalanceState:
    """Rolling counts of Max publishes by domestic vs outbound pillar."""

    benefit_counts: Counter[str] = field(default_factory=Counter)
    window_size: int = 12

    def observe(self, benefit: Benefit | None) -> None:
        if benefit:
            self.benefit_counts[benefit] += 1

    @property
    def total(self) -> int:
        return sum(self.benefit_counts.values())

    def domestic_share(self) -> float:
        total = self.total or 1
        domestic = self.benefit_counts.get("local_leisure", 0) + self.benefit_counts.get(
            "domestic_trip", 0
        )
        return domestic / total

    def outbound_share(self) -> float:
        total = self.total or 1
        return self.benefit_counts.get("outbound_trip_from_ru", 0) / total


@dataclass(slots=True)
class MaxTopicEvaluation:
    decision: MaxAudienceDecision
    domestic_or_outbound: DomesticOrOutbound | None
    region_allowed: bool
    calendar: RussiaCalendarContext
    rank_boost: float
    should_publish: bool
    skip_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "audience": self.decision.as_dict(),
            "domestic_or_outbound": self.domestic_or_outbound,
            "region_allowed": self.region_allowed,
            "calendar_label": self.calendar.label,
            "is_leisure_priority_day": self.calendar.is_leisure_priority_day,
            "rank_boost": self.rank_boost,
            "should_publish": self.should_publish,
            "skip_reason": self.skip_reason,
        }


class MaxRussiaEditorialPolicy:
    """Single entry point for Max topic selection rules (addendum §6.1)."""

    def __init__(
        self,
        *,
        domestic_share_target: float = 0.75,
        outbound_share_target: float = 0.25,
        max_capital_share: float = 0.4,
        gate: MaxRussiaAudienceGate | None = None,
        regions: RussianRegionCoveragePlanner | None = None,
        balance: MaxBalanceState | None = None,
    ) -> None:
        self.domestic_share_target = domestic_share_target
        self.outbound_share_target = outbound_share_target
        self.gate = gate or MaxRussiaAudienceGate()
        self.regions = regions or RussianRegionCoveragePlanner(max_capital_share=max_capital_share)
        self.balance = balance or MaxBalanceState()

    def evaluate(
        self,
        *,
        geo: TopicGeo,
        intent: str | None = None,
        topic_id: str | None = None,
        entity_name: str | None = None,
        city_name: str | None = None,
        practicality_verified: bool = False,
        entry_rules_mentioned: bool = False,
        expired_local_event: bool = False,
        product_available_on_ru_store: bool | None = None,
        day: dt.date | None = None,
        enforce_region_cap: bool = True,
        enforce_balance_soft: bool = True,
    ) -> MaxTopicEvaluation:
        calendar = russia_calendar_context(day)
        decision = self.gate.evaluate(
            geo=geo,
            intent=intent,
            topic_id=topic_id,
            entity_name=entity_name,
            practicality_verified=practicality_verified,
            entry_rules_mentioned=entry_rules_mentioned,
            expired_local_event=expired_local_event,
            product_available_on_ru_store=product_available_on_ru_store,
        )

        domestic_or_outbound: DomesticOrOutbound | None = None
        if decision.benefit in {"local_leisure", "domestic_trip", "russia_relevant_news"}:
            domestic_or_outbound = "domestic"
        elif decision.benefit == "outbound_trip_from_ru":
            domestic_or_outbound = "outbound"

        region_key = normalize_region_key(city_name) or normalize_region_key(geo.city_id)
        region_allowed = True
        if geo.is_russia:
            region_allowed = self.regions.allows(city_id=geo.city_id, city_name=city_name)
            decision.covered_region_ids = (
                [region_key] if region_key else list(decision.covered_region_ids)
            )

        rank_boost = 0.0
        if geo.is_russia:
            rank_boost += self.regions.rank_boost(city_id=geo.city_id, city_name=city_name)
        if calendar.is_leisure_priority_day and decision.benefit == "local_leisure":
            rank_boost += 0.15
        if calendar.is_fixed_holiday and domestic_or_outbound == "domestic":
            rank_boost += 0.1

        # Soft balance: prefer under-filled pillar without hard-blocking news.
        if enforce_balance_soft and self.balance.total >= 4 and domestic_or_outbound:
            if (
                domestic_or_outbound == "outbound"
                and self.balance.outbound_share() >= self.outbound_share_target + 0.15
            ):
                rank_boost -= 0.25
            if (
                domestic_or_outbound == "domestic"
                and self.balance.domestic_share() >= self.domestic_share_target + 0.15
            ):
                rank_boost -= 0.1

        should_publish = decision.should_publish
        skip_reason: str | None = None
        if not decision.should_publish:
            skip_reason = decision.reason or "audience_gate"
        elif enforce_region_cap and geo.is_russia and not region_allowed:
            should_publish = False
            skip_reason = "region_diversity_capital_share"
        elif decision.relevance_for_russia == "none":
            should_publish = False
            skip_reason = "no_russia_relevance"

        return MaxTopicEvaluation(
            decision=decision,
            domestic_or_outbound=domestic_or_outbound,
            region_allowed=region_allowed,
            calendar=calendar,
            rank_boost=rank_boost,
            should_publish=should_publish,
            skip_reason=skip_reason,
        )

    def observe_publish(self, evaluation: MaxTopicEvaluation) -> None:
        """Record a successful Max publish for rolling diversity/balance."""
        self.balance.observe(evaluation.decision.benefit)
        for region in evaluation.decision.covered_region_ids:
            self.regions.state.observe(region)


__all__ = [
    "DomesticOrOutbound",
    "MaxBalanceState",
    "MaxRussiaEditorialPolicy",
    "MaxTopicEvaluation",
]
