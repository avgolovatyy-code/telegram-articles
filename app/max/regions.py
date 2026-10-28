"""Regional diversity planner for Max Russia audience (addendum §6.1.3)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

#: Starter hubs — not an exclusive list; other cities allowed when themes exist.
RUSSIA_REGION_HUBS: tuple[str, ...] = (
    "moscow",
    "saint_petersburg",
    "st_petersburg",
    "petersburg",
    "kazan",
    "nizhny_novgorod",
    "ekaterinburg",
    "yekaterinburg",
    "novosibirsk",
    "kaliningrad",
    "sochi",
    "krasnodar",
)


def normalize_region_key(name_or_id: str | None) -> str | None:
    if not name_or_id:
        return None
    key = name_or_id.casefold().strip()
    key = key.replace("ё", "е")
    for src, dst in (
        ("санкт-петербург", "saint_petersburg"),
        ("петербург", "saint_petersburg"),
        ("спб", "saint_petersburg"),
        ("москва", "moscow"),
        ("казань", "kazan"),
        ("нижний новгород", "nizhny_novgorod"),
        ("екатеринбург", "ekaterinburg"),
        ("новосибирск", "novosibirsk"),
        ("калининград", "kaliningrad"),
        ("сочи", "sochi"),
        ("краснодар", "krasnodar"),
    ):
        if src in key:
            return dst
    return key.replace(" ", "_").replace("-", "_")


@dataclass(slots=True)
class RegionCoverageState:
    """Rolling counts of Max publishes by city/region key."""

    city_counts: Counter[str]
    window_size: int = 12

    @classmethod
    def empty(cls, *, window_size: int = 12) -> RegionCoverageState:
        return cls(city_counts=Counter(), window_size=window_size)

    def observe(self, region_key: str | None) -> None:
        key = normalize_region_key(region_key)
        if key:
            self.city_counts[key] += 1

    def recent_share(self, region_key: str | None) -> float:
        key = normalize_region_key(region_key)
        total = sum(self.city_counts.values()) or 1
        if not key:
            return 0.0
        return self.city_counts[key] / total


class RussianRegionCoveragePlanner:
    """Prefer under-covered Russian hubs; avoid Moscow/SPb monopoly."""

    def __init__(
        self,
        state: RegionCoverageState | None = None,
        *,
        max_capital_share: float = 0.4,
    ) -> None:
        self.state = state or RegionCoverageState.empty()
        self.max_capital_share = max_capital_share
        self._capitals = {"moscow", "saint_petersburg", "st_petersburg", "petersburg"}

    def allows(self, *, city_id: str | None, city_name: str | None = None) -> bool:
        key = normalize_region_key(city_name) or normalize_region_key(city_id)
        if not key:
            return True
        if key not in self._capitals:
            return True
        # Capitals OK until they dominate the recent window.
        return self.state.recent_share(key) < self.max_capital_share

    def rank_boost(self, *, city_id: str | None, city_name: str | None = None) -> float:
        """Higher is better — underused hubs get a boost."""
        key = normalize_region_key(city_name) or normalize_region_key(city_id)
        if not key:
            return 0.0
        share = self.state.recent_share(key)
        if key in self._capitals:
            return max(0.0, 0.3 - share)
        if any(hub in key for hub in RUSSIA_REGION_HUBS):
            return max(0.0, 0.5 - share)
        return max(0.0, 0.2 - share)


__all__ = [
    "RUSSIA_REGION_HUBS",
    "RegionCoverageState",
    "RussianRegionCoveragePlanner",
    "normalize_region_key",
]
