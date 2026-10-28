"""Editorial Engine 3.0: footers, RU demand, mechanics, MAX culture gate."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.editorial.curiosity import curiosity_candidates
from app.editorial.demo_plan import SAMPLE_DRAFTS, build_three_channel_plan, drafts_for
from app.editorial.footer import (
    MAX_PUBLIC_URL,
    TELEGRAM_RU_URL,
    inject_max_html,
    inject_plain_text,
    inject_telegram_rich,
    ru_cross_promo_in_en,
)
from app.editorial.mechanics import EDITORIAL_MECHANICS
from app.editorial.pillars import accepted_pillar_codes, canonical_pillar, pillar_codes
from app.editorial.practicality import evaluate_practicality, requires_practicality_gate
from app.editorial.russia_demand import OCTOBER_2026_BASELINE, RussiaDemandProvider
from app.editorial.schemas import EditorialDecision
from app.max.audience import MaxRussiaAudienceGate
from app.telegram import blocks as tb
from app.topics.geo import TopicGeo


def _geo(*, russia: bool, city: str | None = None) -> TopicGeo:
    return TopicGeo(
        country_id="ru" if russia else "fr",
        city_id=city,
        attraction_id=None,
        is_russia=russia,
    )


def test_thirteen_pillars_and_aliases():
    assert len(pillar_codes()) == 13
    assert canonical_pillar("weekend_plans") == "weekend_ideas"
    assert canonical_pillar("deep_guide") == "big_guide"
    assert "weekend_plans" in accepted_pillar_codes()


def test_eight_editorial_mechanics():
    assert len(EDITORIAL_MECHANICS) == 8
    assert "weekend_utility" in EDITORIAL_MECHANICS
    assert "practical_from_russia" in EDITORIAL_MECHANICS


def test_demand_baseline_does_not_collapse_metric_types():
    types = {item.metric_type for item in OCTOBER_2026_BASELINE}
    assert "organized_tour_sales" in types
    assert "hotel_bookings" in types
    turkey = next(item for item in OCTOBER_2026_BASELINE if item.geo == "TR")
    russia = next(item for item in OCTOBER_2026_BASELINE if item.geo == "RU")
    assert turkey.metric_type != russia.metric_type
    assert "≠" in turkey.caveat or "не" in turkey.caveat.casefold()


def test_russia_demand_provider_seeds(session):
    provider = RussiaDemandProvider(session)
    created = provider.seed_baseline()
    assert created >= 8
    payload = provider.brief_payload(as_of=dt.date(2026, 10, 28))
    assert payload["missing_live_trends"]["google_trends"] == "UNAVAILABLE"
    assert payload["outbound_demand_signals"]
    geos = {row["geo"] for row in payload["outbound_demand_signals"]}
    assert "TR" in geos and "EG" in geos and "CN" in geos


def test_culture_does_not_require_practicality_gate():
    assert (
        requires_practicality_gate(
            audience_axis="culture_and_curiosity",
            editorial_mechanic="curious_travel_news",
        )
        is False
    )
    result = evaluate_practicality(
        audience_axis="culture_and_curiosity",
        editorial_mechanic="curious_travel_news",
        claims=["В Париже есть музей Лувр"],
    )
    assert result.status == "not_applicable"


def test_unverified_visa_claim_holds():
    result = evaluate_practicality(
        audience_axis="ru_outbound_trip",
        editorial_mechanic="practical_from_russia",
        claims=["В Китай без визы"],
        verified_entry_rules=False,
        recommends_travel=True,
    )
    assert result.status == "hold"


def test_telegram_ru_footer_injected_once():
    message = tb.rich_message([tb.paragraph("Текст поста")])
    first = inject_telegram_rich(message, market="ru")
    assert first.applied is True
    blob = str(message)
    assert MAX_PUBLIC_URL in blob
    second = inject_telegram_rich(message, market="ru")
    assert second.applied is False
    assert blob.count(MAX_PUBLIC_URL) == 1


def test_telegram_en_rejects_ru_footer():
    text, result = inject_plain_text("Hello from London", market="en")
    assert result.skipped is True
    assert "MAX" not in text
    assert ru_cross_promo_in_en("Ещё мы в MAX — https://max.ru/channel_wegotrip")


def test_max_footer_points_to_telegram_ru():
    html, result = inject_max_html("<h1>Казань</h1><p>План на выходные.</p>")
    assert result.applied is True
    assert TELEGRAM_RU_URL in html
    assert "id7816636266_bot" not in html
    again, second = inject_max_html(html)
    assert second.applied is False
    assert again.count(TELEGRAM_RU_URL) == 1


def test_legacy_max_url_holds():
    _text, result = inject_plain_text(
        "Смотрите https://max.ru/id7816636266_bot", market="ru", html=True
    )
    assert result.hold is True


def test_max_gate_allows_foreign_culture_without_product():
    gate = MaxRussiaAudienceGate()
    decision = gate.evaluate(
        geo=_geo(russia=False, city="paris"),
        intent="museum",
        audience_axis="culture_and_curiosity",
        editorial_mechanic="curious_travel_news",
        product_available_on_ru_store=False,
        recommends_travel=False,
    )
    assert decision.should_publish is True
    assert decision.benefit == "culture_curiosity"


def test_max_gate_still_blocks_practical_foreign_without_store():
    gate = MaxRussiaAudienceGate()
    decision = gate.evaluate(
        geo=_geo(russia=False),
        intent="things_to_do",
        audience_axis="ru_outbound_trip",
        editorial_mechanic="practical_from_russia",
        product_available_on_ru_store=False,
        recommends_travel=True,
    )
    assert decision.should_publish is False


def test_decision_en_cannot_target_max():
    item = EditorialDecision(
        action="add",
        planned_date=dt.date(2026, 11, 1),
        pillar="weekend_ideas",
        format="weekend_digest",
        editorial_mechanic="weekend_utility",
        audience_axis="en_local",
        channel_targets=["telegram_en", "max_ru"],
        product_recommendation="none",
        why_worth_reading_without_purchase="weekend idea",
    ).fill_defaults("en")
    assert item.channel_targets == ["telegram_en"]


def test_diversity_blocks_third_same_mechanic(session, settings):
    from app.db.models import EditorialPlanSlot
    from app.editorial.diversity import reject_reason

    for offset in (2, 1):
        session.add(
            EditorialPlanSlot(
                market="ru",
                slot_date=dt.date(2026, 11, 10) - dt.timedelta(days=offset),
                pillar="travel_news",
                format="short_post",
                audience="both",
                editorial_mechanic="curious_travel_news",
                status="planned",
            )
        )
    session.flush()
    decision = EditorialDecision(
        action="add",
        planned_date=dt.date(2026, 11, 10),
        pillar="hidden_gem",
        format="story_post",
        editorial_mechanic="curious_travel_news",
        audience_axis="culture_and_curiosity",
        product_recommendation="none",
    )
    reason = reject_reason(session, "ru", decision, settings)
    assert reason and "curious_travel_news" in reason


def test_product_optional_is_valid_decision():
    decision = EditorialDecision(
        action="add",
        planned_date=dt.date(2026, 11, 2),
        pillar="place_story",
        format="story_post",
        editorial_mechanic="culture_and_people",
        audience_axis="culture_and_curiosity",
        product_recommendation="none",
        why_worth_reading_without_purchase="история без билета",
    )
    assert decision.product_recommendation == "none"
    assert decision.why_worth_reading_without_purchase


def test_demo_plan_and_twelve_drafts_per_channel():
    plan = build_three_channel_plan(dt.date(2026, 10, 29))
    assert len(plan["telegram_ru"]) >= 20
    assert len(plan["telegram_en"]) >= 16
    assert len(plan["max_ru"]) >= 12
    ru_mechs = {row["editorial_mechanic"] for row in plan["telegram_ru"]}
    assert len(ru_mechs) >= 6
    for channel in ("telegram_ru", "telegram_en", "max_ru"):
        drafts = drafts_for(channel)
        assert len(drafts) >= 12
        assert any(not item["product"] for item in drafts)
        pillars = {item["pillar"] for item in drafts}
        assert len(pillars) >= 6
    assert len(SAMPLE_DRAFTS) >= 36
    assert curiosity_candidates(market="ru")


def test_chief_editor_ru_brief_isolated_from_en(session, settings):
    from app.editorial.brief import build_daily_brief

    ru = build_daily_brief(session, "ru", settings, run_date=dt.date(2026, 10, 28))
    en = build_daily_brief(session, "en", settings, run_date=dt.date(2026, 10, 28))
    assert ru["russia_editorial_market_brief"] is not None
    assert en["russia_editorial_market_brief"] is None
    assert en["localization"]["channel_id"] == "telegram_en"
    assert ru["localization"]["max_channel"]["include_in_ru_decisions"] is True
    assert ru["cultural_and_travel_curiosities"]
    assert en["cultural_and_travel_curiosities"]
    assert ru["events_and_exhibitions"]["status"] == "PARTIAL"
    assert en["events_and_exhibitions"]["status"] == "PARTIAL"
    assert ru["google_trends_signals"]["status"] == "UNAVAILABLE"


def test_seed_creates_demand_rows(session, settings):
    from app.db.models import RussiaDemandObservation
    from app.scheduler.jobs import seed_reference_data

    seed_reference_data(session, settings)
    rows = list(session.scalars(select(RussiaDemandObservation)))
    assert rows
