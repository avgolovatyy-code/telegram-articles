"""Itinerary promise vs body: days, visits, audio-guide duration vs the whole day."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.dzen.products import DzenProductPick, place_tokens
from app.dzen.schemas import DzenArticleAST


def _body(ast: DzenArticleAST) -> str:
    parts = [ast.headline, ast.lead, ast.practical_takeaway]
    for block in ast.blocks:
        if block.text:
            parts.append(block.text)
        parts.extend(block.items)
    return "\n".join(parts)


DAY_HEADING = re.compile(
    r"день\s+(перв|втор|трет|четвёрт|четверт|[1-4])|day\s+[1-4]|"
    r"перв\w+\s+день|втор\w+\s+день",
    re.I,
)
DAY_INDEX = {
    "перв": 1,
    "втор": 2,
    "трет": 3,
    "четвёрт": 4,
    "четверт": 4,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
}
HOLLOW_DAY = re.compile(
    r"выберите\s+(что[- ]нибудь|любое|музей по вкусу)|как получится|"
    r"по желанию без маршрута|свободный вечер без мест",
    re.I,
)
AUDIO_AS_DAY = re.compile(
    r"(это и есть весь\s+(?:перв\w+\s+)?день|аудиогид на весь день|"
    r"весь день занимает|заменяет весь день|весь туристический день)",
    re.I,
)
DURATION_MIN = re.compile(r"(\d+)\s*(?:–|-|—)\s*(\d+)\s*(?:ч|час|h)", re.I)


@dataclass(slots=True)
class ItineraryVisit:
    day: int
    place_name: str
    optional: bool = False


@dataclass(slots=True)
class ItineraryPlan:
    promised_days: int | None
    visits: list[ItineraryVisit] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def promised_days(headline: str) -> int | None:
    folded = (headline or "").casefold().replace("ё", "е")
    digit = re.search(r"(\d+)\s*дн", folded)
    if digit:
        return int(digit.group(1))
    if re.search(r"уикенд|выходн|двухднев", folded):
        return 2
    numbered = (
        ("два", 2),
        ("двух", 2),
        ("три", 3),
        ("трех", 3),
        ("трёх", 3),
        ("четыре", 4),
        ("четырёх", 4),
    )
    for word, count in numbered:
        if re.search(rf"{word}(?:\s+\w+){{0,3}}\s+дн", folded):
            return count
    return None


def _day_number(title: str) -> int | None:
    match = DAY_HEADING.search(title or "")
    if not match:
        return None
    token = (match.group(1) if match.lastindex else match.group(0) or "").casefold()
    for key, value in DAY_INDEX.items():
        if token.startswith(key) or key in token:
            return value
    digits = re.search(r"[1-4]", title)
    return int(digits.group(0)) if digits else None


def build_itinerary(ast: DzenArticleAST) -> ItineraryPlan:
    promised = promised_days(ast.headline)
    visits: list[ItineraryVisit] = []
    current_day = 1
    for block in ast.blocks:
        if block.type == "heading" and block.text:
            numbered = _day_number(block.text)
            if numbered:
                current_day = numbered
            for name in place_tokens(block.text):
                visits.append(ItineraryVisit(day=current_day, place_name=name))
            continue
        blob = " ".join([block.text or "", *block.items])
        if DAY_HEADING.search(blob[:80] or ""):
            numbered = _day_number(blob[:80])
            if numbered:
                current_day = numbered
        for name in place_tokens(blob):
            visits.append(ItineraryVisit(day=current_day, place_name=name))
    return ItineraryPlan(promised_days=promised, visits=visits)


def itinerary_issues(
    ast: DzenArticleAST, products: list[DzenProductPick] | None = None
) -> list[str]:
    text = _body(ast)
    plan = build_itinerary(ast)
    issues: list[str] = []
    if plan.promised_days and plan.promised_days >= 2:
        days_present = {visit.day for visit in plan.visits}
        for day in range(1, plan.promised_days + 1):
            day_visits = [visit for visit in plan.visits if visit.day == day]
            named = {visit.place_name for visit in day_visits}
            if day not in days_present or len(named) < 2:
                issues.append(
                    f"headline_promise_gap: day {day} needs named places, not a leftover slot"
                )
        if HOLLOW_DAY.search(text):
            issues.append("headline_promise_gap: a promised day is delegated to the reader")
    if AUDIO_AS_DAY.search(text):
        issues.append("route_infeasible: audio-guide duration is sold as the whole day")
    for product in products or []:
        minutes = _product_minutes(product)
        if minutes and minutes <= 150 and AUDIO_AS_DAY.search(text):
            issues.append(
                f"route_infeasible: product {product.external_id} duration cannot be the whole day"
            )
    return issues


def _product_minutes(product: DzenProductPick) -> int | None:
    label = product.duration_label or ""
    match = DURATION_MIN.search(label)
    if match:
        return int(match.group(2)) * 60
    snapshot = product.snapshot or {}
    raw = snapshot.get("duration_max") or snapshot.get("duration_min")
    if isinstance(raw, int):
        return raw
    return None


__all__ = [
    "ItineraryPlan",
    "ItineraryVisit",
    "build_itinerary",
    "itinerary_issues",
    "promised_days",
]
