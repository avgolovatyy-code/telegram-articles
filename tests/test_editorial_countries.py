"""Chief Editor destination_country must fit varchar(16) and not poison the session."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text

from app.db.models import EditorialPlanSlot
from app.editorial.chief_editor import ChiefEditorService
from app.editorial.countries import normalize_destination_country
from app.editorial.planner import apply_decision_set
from app.editorial.schemas import EditorialDecision, EditorialDecisionSet


def test_uae_full_name_becomes_iso_code():
    assert normalize_destination_country("United Arab Emirates") == "AE"
    assert normalize_destination_country("uae") == "AE"
    assert normalize_destination_country("ОАЭ") == "AE"
    assert normalize_destination_country("ARE") == "AE"
    assert normalize_destination_country("jp") == "JP"
    assert normalize_destination_country("") is None
    assert normalize_destination_country(None) is None
    long_name = "This is a very long unknown country name"
    assert normalize_destination_country(long_name) == long_name[:16]
    assert len(normalize_destination_country(long_name) or "") <= 16


def test_decision_maps_country_name_before_insert():
    decision = EditorialDecision(
        action="add",
        planned_date=dt.date(2026, 11, 14),
        pillar="trip_planning",
        format="city_micro_itinerary",
        audience="traveler",
        editorial_mechanic="weekend_utility",
        audience_axis="en_trip",
        channel_targets=["telegram_en"],
        destination_country="United Arab Emirates",
        destination_city="Dubai",
        angle="Dubai in one day",
        reader_value="A practical planning framework",
        product_recommendation="none",
    )
    assert decision.destination_country == "AE"


def test_planner_stores_iso_code_not_full_country_name(session, settings):
    decision = EditorialDecision(
        action="add",
        planned_date=dt.date(2026, 11, 14),
        pillar="trip_planning",
        format="city_micro_itinerary",
        audience="traveler",
        editorial_mechanic="weekend_utility",
        audience_axis="en_trip",
        channel_targets=["telegram_en"],
        destination_country="United Arab Emirates",
        destination_city="Dubai",
        angle="Dubai in one day without trying to see everything",
        reader_value="A practical planning framework for travelers with limited time",
        product_recommendation="none",
        needs_human_review=False,
    )
    apply_decision_set(
        session,
        market="en",
        run_date=dt.date(2026, 11, 10),
        decision_set=EditorialDecisionSet(
            market="en",
            run_date=dt.date(2026, 11, 10),
            editorial_thesis="plan",
            daily_summary="summary",
            decisions=[decision],
        ),
        brief={},
        llm_run_id=None,
        settings=settings,
        dry_run=False,
    )
    slot = session.scalars(select(EditorialPlanSlot).where(EditorialPlanSlot.market == "en")).one()
    assert slot.destination_country == "AE"
    assert len(slot.destination_country) <= 16


def test_failed_market_does_not_poison_session(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "openai_chief_editor_daily", True)
    service = ChiefEditorService(session, settings=settings)

    def boom(market, **kwargs):
        session.execute(text("SELECT this_column_does_not_exist FROM editorial_plan_slots"))

    monkeypatch.setattr(service, "_run_market", boom)
    report = service.run(markets=("en", "ru"))
    assert report.ok is False
    assert report.errors
    session.add(
        EditorialPlanSlot(
            market="ru",
            slot_date=dt.date(2026, 11, 11),
            pillar="place_story",
            format="short_post",
            audience="both",
            status="planned",
        )
    )
    session.flush()
    assert session.scalars(select(EditorialPlanSlot)).first() is not None
