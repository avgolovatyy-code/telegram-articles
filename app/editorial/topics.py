"""Create catalog-independent topics so editorial slots can generate without inventory."""

from __future__ import annotations

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import TopicStatus
from app.db.models import EditorialPlanSlot, TopicCandidate


def is_editorial_topic(topic: TopicCandidate | None) -> bool:
    return topic is not None and topic.entity_type == "editorial"


def ensure_editorial_topic(session: Session, slot: EditorialPlanSlot) -> TopicCandidate:
    """Attach a TopicCandidate to ``slot`` so the writer can run without a catalogue hit."""
    key = f"editorial-slot-{slot.id}"
    if slot.topic_id:
        existing = session.get(TopicCandidate, slot.topic_id)
        if (
            existing is not None
            and existing.entity_type == "editorial"
            and existing.topic_key == key
        ):
            if existing.status in {TopicStatus.REJECTED, TopicStatus.USED}:
                existing.status = TopicStatus.CANDIDATE
                existing.generation_failures = 0
            return existing
    found = session.scalar(
        select(TopicCandidate).where(
            TopicCandidate.market == slot.market, TopicCandidate.topic_key == key
        )
    )
    if found is not None:
        if found.status in {TopicStatus.REJECTED, TopicStatus.USED}:
            found.status = TopicStatus.CANDIDATE
            found.generation_failures = 0
        slot.topic_id = found.id
        session.flush()
        return found

    name = (slot.destination_city or slot.angle or slot.pillar or "editorial")[:255]
    query = (slot.angle or slot.reader_value or name)[:500]
    slug = slugify(name)[:240] or f"editorial-{slot.id}"
    topic = TopicCandidate(
        market=slot.market,
        topic_key=key,
        topic_slug=f"{slot.market}-{slug}"[:255],
        entity_type="editorial",
        entity_external_id=f"slot-{slot.id}",
        entity_name=name,
        intent=slot.audience or "both",
        primary_query=query,
        canonical_query=query,
        relevant_product_ids=[],
        inventory_depth=0,
        topic_score=80.0,
        demand_source="editorial_slot",
        requires_volatile_facts=slot.editorial_mechanic == "practical_from_russia",
        status=TopicStatus.CANDIDATE,
        score_breakdown={
            "pillar": slot.pillar,
            "format": slot.format,
            "editorial_mechanic": slot.editorial_mechanic,
            "channel_targets": list(slot.channel_targets or []),
        },
    )
    session.add(topic)
    session.flush()
    slot.topic_id = topic.id
    session.flush()
    return topic


__all__ = ["ensure_editorial_topic", "is_editorial_topic"]
