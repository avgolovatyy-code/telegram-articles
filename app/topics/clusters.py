"""Keyword cluster registry.

Query patterns live in YAML (``app/topics/intents/{market}.yaml``) and are mirrored
into the ``keyword_clusters`` table so an operator can enable, disable or reweight a
cluster from the admin UI without a deploy. Business logic never hardcodes queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MARKETS, Market
from app.db.models import KeywordCluster
from app.topics.morphology import pattern_placeholders

INTENTS_DIR = Path(__file__).parent / "intents"


@dataclass(frozen=True, slots=True)
class ClusterDefinition:
    market: Market
    entity_type: str
    intent: str
    label: str
    primary_pattern: str
    secondary_patterns: tuple[str, ...]
    weight: float = 1.0
    min_inventory: int = 1
    requires_volatile_facts: bool = False
    enabled: bool = True

    @property
    def placeholders(self) -> set[str]:
        names = pattern_placeholders(self.primary_pattern)
        for pattern in self.secondary_patterns:
            names |= pattern_placeholders(pattern)
        return names


@lru_cache(maxsize=4)
def load_seed_clusters(market: Market) -> tuple[ClusterDefinition, ...]:
    path = INTENTS_DIR / f"{market}.yaml"
    if not path.exists():
        return ()
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    definitions: list[ClusterDefinition] = []
    for entry in document.get("clusters", []):
        definitions.append(
            ClusterDefinition(
                market=market,
                entity_type=str(entry["entity_type"]),
                intent=str(entry["intent"]),
                label=str(entry.get("label") or entry["intent"]),
                primary_pattern=str(entry["primary"]),
                secondary_patterns=tuple(str(p) for p in entry.get("secondary", [])),
                weight=float(entry.get("weight", 1.0)),
                min_inventory=int(entry.get("min_inventory", 1)),
                requires_volatile_facts=bool(entry.get("requires_volatile_facts", False)),
                enabled=bool(entry.get("enabled", True)),
            )
        )
    return tuple(definitions)


class KeywordClusterRegistry:
    """Database-backed view of the seed clusters."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def sync_seeds(self) -> int:
        """Insert missing clusters; never overwrite operator edits to existing rows."""
        created = 0
        for market in MARKETS:
            for definition in load_seed_clusters(market):
                existing = self.session.scalar(
                    select(KeywordCluster).where(
                        KeywordCluster.market == definition.market,
                        KeywordCluster.entity_type == definition.entity_type,
                        KeywordCluster.intent == definition.intent,
                    )
                )
                if existing is not None:
                    continue
                self.session.add(
                    KeywordCluster(
                        market=definition.market,
                        entity_type=definition.entity_type,
                        intent=definition.intent,
                        label=definition.label,
                        primary_pattern=definition.primary_pattern,
                        secondary_patterns=list(definition.secondary_patterns),
                        weight=definition.weight,
                        min_inventory=definition.min_inventory,
                        requires_volatile_facts=definition.requires_volatile_facts,
                        enabled=definition.enabled,
                    )
                )
                created += 1
        self.session.flush()
        return created

    def for_entity_type(self, market: Market, entity_type: str) -> list[ClusterDefinition]:
        rows = self.session.scalars(
            select(KeywordCluster).where(
                KeywordCluster.market == market,
                KeywordCluster.entity_type == entity_type,
                KeywordCluster.enabled.is_(True),
            )
        ).all()
        if rows:
            return [_from_row(row) for row in rows]
        return [
            definition
            for definition in load_seed_clusters(market)
            if definition.entity_type == entity_type and definition.enabled
        ]

    def all(self, market: Market) -> list[ClusterDefinition]:
        rows = self.session.scalars(
            select(KeywordCluster).where(
                KeywordCluster.market == market, KeywordCluster.enabled.is_(True)
            )
        ).all()
        if rows:
            return [_from_row(row) for row in rows]
        return [d for d in load_seed_clusters(market) if d.enabled]


def _from_row(row: KeywordCluster) -> ClusterDefinition:
    return ClusterDefinition(
        market=row.market,  # type: ignore[arg-type]
        entity_type=row.entity_type,
        intent=row.intent,
        label=row.label or row.intent,
        primary_pattern=row.primary_pattern,
        secondary_patterns=tuple(row.secondary_patterns or ()),
        weight=row.weight,
        min_inventory=row.min_inventory,
        requires_volatile_facts=row.requires_volatile_facts,
        enabled=row.enabled,
    )


__all__ = ["INTENTS_DIR", "ClusterDefinition", "KeywordClusterRegistry", "load_seed_clusters"]
