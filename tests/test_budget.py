"""AI Budget Manager: the $3/day hard cap and the 10→20 per market ramp."""

from __future__ import annotations

import datetime as dt

import pytest

from app.ai.budget import RESERVATION_HELD, BudgetManager
from app.ai.pricing import approx_tokens, estimate_cost, get_price
from app.db.models import Article, BudgetReservation
from app.db.types import utcnow
from app.errors import BudgetExceeded


def make_article(session, market: str, cost: float) -> Article:
    article = Article(
        public_id=f"a{market}{cost}{utcnow().timestamp()}",
        market=market,
        topic_slug="t",
        entity_type="city",
        entity_external_id="1",
        entity_name="City",
        intent="things_to_do",
        primary_query="q",
        status="draft",
        actual_cost_usd=cost,
        generation_attempts=1,
    )
    session.add(article)
    session.flush()
    return article


def test_model_prices_match_the_published_catalogue():
    assert get_price("gpt-5.6-terra").input_per_mtok == 2.00
    assert get_price("gpt-5.6-terra").output_per_mtok == 12.00
    assert get_price("gpt-5.6-luna").input_per_mtok == 0.20
    assert get_price("gpt-5.6-sol").output_per_mtok == 20.00


def test_unknown_model_uses_the_pessimistic_fallback():
    assert get_price("gpt-9-unreleased").input_per_mtok == 4.00


def test_estimate_includes_web_search_and_images():
    with_tools = estimate_cost(
        "gpt-5.6-luna", input_tokens=1000, output_tokens=500, web_search_calls=2
    )
    without = estimate_cost("gpt-5.6-luna", input_tokens=1000, output_tokens=500)
    assert with_tools > without
    assert pytest.approx(with_tools - without, abs=1e-9) == 0.02


def test_cached_input_is_cheaper():
    full = estimate_cost("gpt-5.6-terra", input_tokens=100_000, output_tokens=0)
    cached = estimate_cost(
        "gpt-5.6-terra", input_tokens=100_000, output_tokens=0, cached_input_tokens=100_000
    )
    assert cached < full


def test_approx_tokens_is_positive():
    assert approx_tokens("hello world") > 0


def test_spend_and_remaining(session, settings):
    manager = BudgetManager(session, settings)
    assert manager.spent() == 0.0
    manager.record(amount_usd=0.5, market="en", task="article_write", model="gpt-5.6-terra")
    snapshot = manager.snapshot()
    assert snapshot.spent_usd == 0.5
    assert snapshot.remaining_usd == pytest.approx(2.5)


def test_reservation_counts_against_the_budget(session, settings):
    manager = BudgetManager(session, settings)
    manager.reserve("en", 1.0)
    snapshot = manager.snapshot()
    assert snapshot.reserved_usd == 1.0
    assert snapshot.remaining_usd == pytest.approx(2.0)


def test_reserve_refuses_to_break_the_cap(session, settings):
    manager = BudgetManager(session, settings)
    manager.record(amount_usd=2.95, market="en")
    with pytest.raises(BudgetExceeded):
        manager.reserve("en", 0.5)


def test_hard_cap_detection(session, settings):
    manager = BudgetManager(session, settings)
    manager.record(amount_usd=3.0, market="en")
    assert manager.hard_cap_reached()
    assert not manager.can_start_article("en").allowed


def test_no_ceiling_by_default_so_the_budget_is_the_only_limit(session, settings):
    """A cheap day may produce well over 20 articles per market."""
    assert settings.articles_max_per_day("en") is None
    manager = BudgetManager(session, settings)
    for _ in range(25):
        make_article(session, "en", 0.001)
    assert manager.can_start_article("en").allowed


def test_an_explicit_ceiling_is_still_honoured(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "en_articles_max_per_day", 20)
    manager = BudgetManager(session, settings)
    for _ in range(20):
        make_article(session, "en", 0.001)
    decision = manager.can_start_article("en")
    assert not decision.allowed
    assert "maximum" in decision.reason


def test_plan_serves_both_minimums_before_growing(session, settings):
    manager = BudgetManager(session, settings)
    plan = manager.plan_daily_generation()
    assert plan["en"] >= settings.en_articles_min_per_day
    assert plan["ru"] >= settings.ru_articles_min_per_day


def test_a_cheap_day_plans_more_than_twenty_per_market(session, settings):
    """$3 at ~$0.05 per article funds far more than the old 20-per-market cap."""
    for _ in range(4):
        make_article(session, "en", 0.03)
    plan = BudgetManager(session, settings).plan_daily_generation()
    assert plan["en"] + plan["ru"] > 40
    assert plan["en"] > 20


def test_the_plan_never_exceeds_the_daily_budget(session, settings):
    manager = BudgetManager(session, settings)
    make_article(session, "en", 0.05)
    plan = manager.plan_daily_generation()
    projected = (plan["en"] + plan["ru"]) * manager.average_article_cost()
    assert projected <= settings.daily_ai_budget_usd


def test_plan_prioritises_minimums_when_the_budget_is_tight(session, settings):
    manager = BudgetManager(session, settings)
    # Leave room for roughly 12 articles at the default estimate.
    manager.record(amount_usd=settings.daily_ai_budget_usd - 1.08, market="en")
    plan = manager.plan_daily_generation()
    total = plan["en"] + plan["ru"]
    assert total > 0
    # Neither market may be starved while both are below their minimum.
    assert plan["en"] > 0 and plan["ru"] > 0
    assert abs(plan["en"] - plan["ru"]) <= 1


def test_plan_is_empty_when_the_budget_is_gone(session, settings):
    manager = BudgetManager(session, settings)
    manager.record(amount_usd=3.0, market="en")
    assert manager.plan_daily_generation() == {"en": 0, "ru": 0}


def test_rolling_average_uses_actual_cost(session, settings):
    manager = BudgetManager(session, settings)
    make_article(session, "en", 0.06)
    make_article(session, "ru", 0.10)
    assert manager.average_article_cost() == pytest.approx(0.08)


def test_stale_reservations_are_released(session, settings):
    manager = BudgetManager(session, settings)
    reservation = BudgetReservation(
        spend_date=utcnow().date(),
        market="en",
        amount_usd=1.0,
        status=RESERVATION_HELD,
        created_at=utcnow() - dt.timedelta(hours=2),
    )
    session.add(reservation)
    session.flush()
    assert manager.expire_stale_reservations() == 1
    assert manager.reserved() == 0.0


def test_settled_reservation_stops_counting(session, settings):
    manager = BudgetManager(session, settings)
    reservation = manager.reserve("ru", 0.5)
    manager.settle(reservation)
    assert manager.reserved() == 0.0


def test_estimate_article_cost_is_within_the_per_article_envelope(session, settings):
    manager = BudgetManager(session, settings)
    estimate = manager.estimate_article_cost(
        writer_model=settings.openai_writer_model,
        review_model=settings.review_model,
        context_chars=12_000,
        expected_output_chars=10_000,
        web_search_calls=2,
    )
    # 20 EN + 20 RU per day must stay inside $3.
    assert estimate < settings.daily_ai_budget_usd / 20
