"""Editorial slots must generate and publish without the v1 catalog mill."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from app.db.enums import ArticleStatus, PublicationTarget
from app.db.models import Article, EditorialPlanSlot
from app.db.types import utcnow
from app.editorial.eligibility import publication_allowed
from app.editorial.planner import promote_auto_review_slots, slots_ready_for_generation
from app.editorial.topics import ensure_editorial_topic
from app.generation.quality import QualityGate
from app.scheduler import jobs
from app.slack.commands import CommandHandler
from app.slack.notifications import SlackNotifier
from app.telegram.blocks import heading, paragraph, rich_message


def _slot(session, *, market="ru", status="needs_review", hold=False) -> EditorialPlanSlot:
    today = utcnow().date()
    slot = EditorialPlanSlot(
        market=market,
        slot_date=today,
        pillar="place_story",
        format="short_post",
        audience="local",
        angle="Казань: один двор, если вы уже в городе",
        reader_value="Локальная прогулка без витрины",
        editorial_mechanic="short_fact_plus_use",
        audience_axis="ru_local_leisure",
        channel_targets=["telegram_ru", "max_ru"],
        status=status,
        needs_human_review=status == "needs_review",
        payload={"travel_practicality_status": "hold" if hold else "not_applicable"},
    )
    session.add(slot)
    session.flush()
    return slot


def test_auto_publish_promotes_review_slots(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "auto_publish_ru", True)
    slot = _slot(session)
    n = promote_auto_review_slots(session, settings)
    session.refresh(slot)
    assert n == 1
    assert slot.status == "planned"
    assert slot.needs_human_review is False
    assert slot.topic_id is not None


def test_hold_slots_stay_in_review(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "auto_publish_ru", True)
    slot = _slot(session, hold=True)
    n = promote_auto_review_slots(session, settings)
    session.refresh(slot)
    assert n == 0
    assert slot.status == "needs_review"


def test_ready_slots_do_not_need_catalog_topic(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "auto_publish_ru", True)
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    _slot(session)
    ready = slots_ready_for_generation(session, "ru", settings, limit=3)
    assert len(ready) == 1
    assert ready[0].topic_id is not None
    topic = ensure_editorial_topic(session, ready[0])
    assert topic.entity_type == "editorial"


def test_catalog_topic_on_slot_is_replaced(session, settings, monkeypatch):
    from app.db.enums import TopicStatus
    from app.db.models import TopicCandidate

    monkeypatch.setattr(settings, "auto_publish_ru", True)
    mill = TopicCandidate(
        market="ru",
        topic_key="ru:city:london:things_to_do",
        topic_slug="ru-london-audio",
        entity_type="city",
        entity_external_id="1",
        entity_name="London",
        intent="things_to_do",
        primary_query="аудиогид по Лондону",
        canonical_query="аудиогид по Лондону",
        status=TopicStatus.CANDIDATE,
    )
    session.add(mill)
    session.flush()
    slot = _slot(session)
    slot.topic_id = mill.id
    session.flush()
    topic = ensure_editorial_topic(session, slot)
    session.refresh(slot)
    assert topic.entity_type == "editorial"
    assert topic.primary_query != "аудиогид по Лондону"
    assert slot.topic_id == topic.id
    assert slot.topic_id != mill.id


def test_schedule_ignores_catalog_mill_when_legacy_off(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "editorial_v2_dry_run", False)
    monkeypatch.setattr(settings, "old_article_auto_scheduler_enabled", False)
    monkeypatch.setattr(settings, "auto_publish_ru", True)
    monkeypatch.setattr(settings, "editorial_spec_cutoff_date", dt.date(2026, 10, 28))
    article = Article(
        public_id="legacy-mill",
        market="ru",
        topic_slug="ru-london",
        entity_type="city",
        entity_external_id="1",
        entity_name="London",
        intent="things_to_do",
        primary_query="аудиогид по Лондону",
        status=ArticleStatus.NEEDS_REVIEW,
        current_version=1,
        rendered_message=rich_message([heading("T", 1), paragraph("Body")]),
        body={"title": "T", "intro": "Body", "sections": []},
        products_refreshed_at=utcnow(),
        created_at=dt.datetime(2026, 10, 29, tzinfo=dt.UTC),
    )
    session.add(article)
    session.flush()
    report = jobs.schedule_publications(session, markets=("ru",), settings=settings)
    assert report.details["ru_scheduled"] == 0
    ok, reason = publication_allowed(article, settings, PublicationTarget.PRODUCTION)
    assert not ok
    assert "legacy" in reason


def test_quality_gate_allows_short_editorial_post(settings):
    topic = SimpleNamespace(
        entity_type="editorial",
        entity_name="Казань",
        primary_query="Казань: один двор",
        inventory_depth=0,
    )
    document = SimpleNamespace(
        title="Казань без открытки",
        intro="Один двор и короткий маршрут.",
        sections=[SimpleNamespace(heading="Двор", blocks=[])],
        product_placements=[],
        media_placements=[],
        hashtags=[],
        char_count=lambda: 400,
        plain_text=lambda: "Казань без открытки. Один двор и короткий маршрут.",
    )
    context = SimpleNamespace(
        market="ru",
        topic=topic,
        products=[],
        media=[],
        catalog_attractions=[],
        catalog_facts=[],
    )
    result = QualityGate(settings).evaluate(document, context, rendered_urls=[])  # type: ignore[arg-type]
    assert result.passed, result.errors


def test_editorial_critic_does_not_require_mill_product_score(settings):
    from app.generation.schemas import QualityReview

    review = QualityReview(
        usefulness=0.8,
        factuality=0.99,
        readability=0.8,
        search_intent_match=0.75,
        natural_language=0.8,
        product_relevance=0.1,
        spam_risk=0.0,
        issues=["no product cards"],
    )
    topic = SimpleNamespace(entity_type="editorial")
    context = SimpleNamespace(topic=topic)
    monkey_settings = settings
    result = QualityGate(monkey_settings).review_thresholds(review, context)  # type: ignore[arg-type]
    assert result.passed, result.errors


def test_coverage_command_uses_editorial_calendar(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "auto_publish_ru", True)
    _slot(session)
    text = CommandHandler(session, settings).handle("coverage")
    blob = str(text)
    assert "осталось тем" not in blob
    assert "календар" in blob.casefold()


def test_pending_hides_catalog_mill_drafts(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "old_article_auto_scheduler_enabled", False)
    article = Article(
        public_id="legacy-pending",
        market="ru",
        topic_slug="ru-london",
        entity_type="city",
        entity_external_id="1",
        entity_name="London",
        intent="things_to_do",
        primary_query="аудиогид по Лондону",
        status=ArticleStatus.NEEDS_REVIEW,
        current_version=1,
        rendered_message=rich_message([heading("T", 1), paragraph("Body")]),
        body={"title": "T", "intro": "Body", "sections": []},
        products_refreshed_at=utcnow(),
    )
    session.add(article)
    session.flush()
    blob = str(CommandHandler(session, settings).handle("pending"))
    assert "аудиогид по Лондону" not in blob
    assert "Очередь пуста" in blob


def test_digest_skips_catalog_leftover_when_v2_on(session, settings, monkeypatch):
    from app.slack.client import NullSlackClient

    class Capture(NullSlackClient):
        def __init__(self, settings):
            super().__init__(settings)
            self.blocks: list = []

        def post_message(self, *, blocks, text, channel=None):
            self.blocks = blocks
            return super().post_message(blocks=blocks, text=text, channel=channel)

    monkeypatch.setattr(settings, "editorial_v2_enabled", True)
    monkeypatch.setattr(settings, "slack_enabled", True)
    monkeypatch.setattr(settings, "slack_channel", "#content")
    client = Capture(settings)
    SlackNotifier(session, settings, client=client).daily_digest()
    assert client.sent
    payload = str(client.blocks)
    assert "осталось тем" not in payload
    assert "календар" in payload.casefold()
