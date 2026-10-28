"""Russian calendar helpers for Max editorial scheduling (addendum §6.1.4).

Official non-working holidays of the Russian Federation (fixed dates).
Transfer days / long weekends vary yearly — treat transfer overlays as optional
config, never invent transfers without a source.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

#: Fixed federal holiday month-day pairs (Labour Code baseline).
RU_FIXED_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 1),  # New Year holidays start
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (1, 6),
        (1, 7),  # Orthodox Christmas
        (1, 8),
        (2, 23),  # Defender of the Fatherland Day
        (3, 8),  # International Women's Day
        (5, 1),  # Spring and Labour Day
        (5, 9),  # Victory Day
        (6, 12),  # Russia Day
        (11, 4),  # Unity Day
    }
)


@dataclass(frozen=True, slots=True)
class RussiaCalendarContext:
    date: dt.date
    is_weekend: bool
    is_fixed_holiday: bool
    is_long_weekend_candidate: bool
    label: str

    @property
    def is_leisure_priority_day(self) -> bool:
        """Thu/Fri before weekend or holiday — good for 'куда сходить' slots."""
        return self.date.weekday() in {3, 4} or self.is_fixed_holiday or self.is_weekend


def russia_calendar_context(
    day: dt.date | None = None,
    *,
    extra_non_working: set[dt.date] | None = None,
) -> RussiaCalendarContext:
    day = day or dt.datetime.now(dt.UTC).date()
    fixed = (day.month, day.day) in RU_FIXED_HOLIDAYS
    extra = bool(extra_non_working and day in extra_non_working)
    weekend = day.weekday() >= 5
    non_working = fixed or extra or weekend
    # Long weekend heuristic: Fri–Mon cluster around a holiday (no invented transfers).
    long_weekend = False
    if fixed or extra:
        long_weekend = True
    elif weekend:
        # Check neighbouring fixed holidays within ±1 day
        for delta in (-1, 1):
            neighbour = day + dt.timedelta(days=delta)
            if (neighbour.month, neighbour.day) in RU_FIXED_HOLIDAYS:
                long_weekend = True
                break

    if fixed:
        label = "ru_fixed_holiday"
    elif extra:
        label = "ru_transfer_or_extra"
    elif weekend:
        label = "weekend"
    elif day.weekday() in {3, 4}:
        label = "pre_weekend"
    else:
        label = "weekday"

    return RussiaCalendarContext(
        date=day,
        is_weekend=weekend,
        is_fixed_holiday=fixed or extra,
        is_long_weekend_candidate=long_weekend and non_working,
        label=label,
    )


def upcoming_ru_leisure_window(
    start: dt.date | None = None,
    *,
    days: int = 14,
) -> list[RussiaCalendarContext]:
    start = start or dt.datetime.now(dt.UTC).date()
    return [russia_calendar_context(start + dt.timedelta(days=offset)) for offset in range(days)]


__all__ = [
    "RU_FIXED_HOLIDAYS",
    "RussiaCalendarContext",
    "russia_calendar_context",
    "upcoming_ru_leisure_window",
]
