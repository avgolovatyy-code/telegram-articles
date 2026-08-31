"""The daily target is a ceiling: the engine stops when material runs out."""

from __future__ import annotations

from app.ai.mock_provider import MockLLMProvider
from app.ai.router import LLMGateway
from app.db.enums import TopicStatus
from app.db.models import Product, TopicCandidate
from app.scheduler import jobs
from app.topics.coverage import assess_coverage
from app.topics.discovery import TopicDiscoveryService, select_topics_for_generation


def add_topic(session, *, score: float, status: str = TopicStatus.CANDIDATE, index: int = 0):
    topic = TopicCandidate(
        market="en",
        topic_key=f"en:city:{index}:things_to_do",
        topic_slug=f"en-city-{index}",
        entity_type="city",
        entity_external_id=str(index),
        entity_name=f"City {index}",
        intent="things_to_do",
        primary_query=f"things to do in City {index}",
        canonical_query=f"city{index} do things",
        topic_score=score,
        status=status,
    )
    session.add(topic)
    session.flush()
    return topic


def test_empty_catalogue_is_reported_as_exhausted(session, settings):
    report = assess_coverage(session, "en", settings)
    assert report.exhausted
    assert "catalogue is empty" in report.reason


def test_weak_candidates_are_left_unwritten(session, settings):
    session.add(Product(market="en", external_id="1", slug="s", title="T"))
    add_topic(session, score=settings.min_topic_score - 0.1, index=1)

    report = assess_coverage(session, "en", settings)

    assert report.exhausted
    assert report.below_threshold == 1
    assert report.usable_candidates == 0
    assert "MIN_TOPIC_SCORE" in report.reason
    assert select_topics_for_generation(session, "en", 10, settings=settings) == []


def test_a_strong_candidate_is_not_exhausted(session, settings):
    session.add(Product(market="en", external_id="1", slug="s", title="T"))
    add_topic(session, score=settings.min_topic_score + 0.2, index=2)

    report = assess_coverage(session, "en", settings)

    assert not report.exhausted
    assert report.usable_candidates == 1
    assert len(select_topics_for_generation(session, "en", 10, settings=settings)) == 1


def test_fully_written_catalogue_reports_exhaustion(session, settings):
    session.add(Product(market="en", external_id="1", slug="s", title="T"))
    add_topic(session, score=0.9, status=TopicStatus.USED, index=3)

    report = assess_coverage(session, "en", settings)

    assert report.exhausted
    assert report.used_topics == 1
    assert "already covered" in report.reason
    assert report.coverage_ratio == 1.0


def test_boost_can_lift_a_candidate_over_the_floor(session, settings):
    session.add(Product(market="en", external_id="1", slug="s", title="T"))
    topic = add_topic(session, score=settings.min_topic_score - 0.05, index=4)
    assert select_topics_for_generation(session, "en", 10, settings=settings) == []

    topic.boost = 0.2
    session.flush()

    assert len(select_topics_for_generation(session, "en", 10, settings=settings)) == 1


def test_generation_stops_and_explains_itself(synced_session, settings, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.jobs.LLMGateway",
        lambda session, settings=None, budget=None: LLMGateway(
            session, MockLLMProvider(), settings=settings, budget=budget
        ),
    )
    # No discovery run: there are products but no topic candidates at all.
    report = jobs.generate_daily_articles(synced_session, markets=("en",), settings=settings)

    assert report.details["en_generated"] == 0
    assert "en_exhausted" in report.details
    assert "already covered" in report.details["en_exhausted"]


def test_a_topic_that_keeps_failing_is_retired(synced_session, settings, monkeypatch):
    """A doomed topic must not be retried, and paid for, on every run."""
    monkeypatch.setattr(settings, "max_topic_generation_failures", 2)
    gateway = LLMGateway(synced_session, MockLLMProvider(fail_quality=True), settings=settings)
    from app.generation.pipeline import GenerationPipeline

    pipeline = GenerationPipeline(synced_session, gateway, settings=settings)
    TopicDiscoveryService(synced_session, settings=settings).discover("en", limit=20)
    topic = select_topics_for_generation(synced_session, "en", 1, settings=settings)[0]

    first = pipeline.generate(topic)
    assert not first.ok
    assert topic.generation_failures == 1
    assert topic.status == TopicStatus.CANDIDATE

    second = pipeline.generate(topic)
    assert not second.ok
    assert topic.generation_failures == 2
    assert topic.status == TopicStatus.REJECTED
    assert "retired after 2 failed generations" in (topic.status_reason or "")

    # A retired topic is no longer offered for generation.
    assert topic.id not in {
        candidate.id
        for candidate in select_topics_for_generation(synced_session, "en", 50, settings=settings)
    }


def test_discovery_reports_coverage(synced_session, settings):
    TopicDiscoveryService(synced_session, settings=settings).discover("en", limit=40)
    report = jobs.discover_topics(synced_session, markets=("en",), settings=settings)
    coverage = report.details["en"]["coverage"]
    assert coverage["usable_candidates"] > 0
    assert coverage["exhausted"] is False
