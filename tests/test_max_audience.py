"""Max Russia-only audience, region diversity and holiday helpers."""

from __future__ import annotations

import datetime as dt

from app.max.audience import MaxRussiaAudienceGate
from app.max.holidays import russia_calendar_context
from app.max.policy import MaxRussiaEditorialPolicy
from app.max.regions import RegionCoverageState, RussianRegionCoveragePlanner
from app.topics.geo import TopicGeo


def _geo(*, russia: bool, city: str | None = None) -> TopicGeo:
    return TopicGeo(
        country_id="ru" if russia else "es",
        city_id=city,
        attraction_id=None,
        is_russia=russia,
    )


def test_audience_allows_domestic_russia():
    gate = MaxRussiaAudienceGate()
    decision = gate.evaluate(geo=_geo(russia=True, city="moscow"), intent="weekend")
    assert decision.should_publish is True
    assert decision.relevance_for_russia == "high"
    assert decision.benefit == "local_leisure"
    assert decision.audience_country == "RU"


def test_audience_allows_outbound_from_ru_catalogue():
    gate = MaxRussiaAudienceGate()
    decision = gate.evaluate(
        geo=_geo(russia=False, city="barcelona"),
        intent="things_to_do",
        entity_name="Барселона",
        product_available_on_ru_store=True,
    )
    assert decision.should_publish is True
    assert decision.benefit == "outbound_trip_from_ru"


def test_audience_blocks_foreign_without_ru_store():
    gate = MaxRussiaAudienceGate()
    decision = gate.evaluate(
        geo=_geo(russia=False),
        intent="things_to_do",
        product_available_on_ru_store=False,
    )
    assert decision.should_publish is False
    assert decision.relevance_for_russia == "none"


def test_audience_blocks_expat_foreign_local():
    gate = MaxRussiaAudienceGate()
    decision = gate.evaluate(geo=_geo(russia=False), intent="expat_neighbourhood")
    assert decision.should_publish is False


def test_audience_blocks_expired_local_event():
    gate = MaxRussiaAudienceGate()
    decision = gate.evaluate(
        geo=_geo(russia=True, city="kazan"),
        intent="exhibition",
        expired_local_event=True,
    )
    assert decision.should_publish is False


def test_region_planner_caps_capital_monopoly():
    state = RegionCoverageState.empty()
    for _ in range(8):
        state.observe("moscow")
    state.observe("kazan")
    planner = RussianRegionCoveragePlanner(state, max_capital_share=0.4)
    assert planner.allows(city_id="moscow") is False
    assert planner.allows(city_id="kazan") is True
    assert planner.rank_boost(city_id="novosibirsk") > planner.rank_boost(city_id="moscow")


def test_russia_fixed_holidays():
    ctx = russia_calendar_context(dt.date(2026, 5, 9))
    assert ctx.is_fixed_holiday is True
    assert ctx.label == "ru_fixed_holiday"
    weekend = russia_calendar_context(dt.date(2026, 10, 31))  # Saturday
    assert weekend.is_weekend is True


def test_policy_skips_when_capitals_dominate():
    policy = MaxRussiaEditorialPolicy(max_capital_share=0.4)
    for _ in range(10):
        policy.regions.state.observe("moscow")
    evaluation = policy.evaluate(
        geo=_geo(russia=True, city="moscow"),
        intent="weekend",
        city_name="Москва",
    )
    assert evaluation.should_publish is False
    assert evaluation.skip_reason == "region_diversity_capital_share"


def test_policy_allows_regional_hub():
    policy = MaxRussiaEditorialPolicy()
    evaluation = policy.evaluate(
        geo=_geo(russia=True, city="kazan"),
        intent="museum",
        city_name="Казань",
        day=dt.date(2026, 11, 4),  # Unity Day
    )
    assert evaluation.should_publish is True
    assert evaluation.domestic_or_outbound == "domestic"
    assert evaluation.calendar.is_fixed_holiday is True
    assert evaluation.rank_boost > 0
