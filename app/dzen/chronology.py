"""Generic chronology and causality checks. Not bound to any city."""

from __future__ import annotations

import re

YEAR = re.compile(r"\b((?:1[0-9]{3})|(?:20[0-2][0-9]))\b")
CAUSE_AFTER = re.compile(
    r"(после|вследствие|из[- ]за|благодаря|по\s+указу|по\s+эдикту|"
    r"стал[аио]?\s+следствием)",
    re.I,
)
BUILT = re.compile(r"(заложи|заложен|постро|основа|возвед|открыл)", re.I)
SENTENCE = re.compile(r"(?<=[.!?…;])\s+|\n+")
VENUE_MISUSE = re.compile(
    r"(мечет|храм|собор|церкв|синагог|костёл|костел|mosque|temple).{0,80}"
    r"(комната для согрев|кафе для обогрев|место погреться|бесплатн\w+\s+грелк)",
    re.I,
)
HOURS_WITHOUT_ASOF = re.compile(
    r"(открыт[аоы]?\s+с\s+\d|работает\s+с\s+\d|часы работы\s*[:—-]\s*\d)",
    re.I,
)
ASOF = re.compile(r"(на\s+\d{1,2}\.\d{1,2}\.\d{4}|по состоянию|проверено|на момент)", re.I)


def _sentences(text: str) -> list[str]:
    parts = SENTENCE.split(text or "")
    return [part.strip() for part in parts if part.strip()]


def chronology_conflicts(text: str) -> list[str]:
    """Fail when a sentence claims an event happened after a year, but also dates it earlier."""
    issues: list[str] = []
    for sentence in _sentences(text):
        years = [int(match.group(1)) for match in YEAR.finditer(sentence)]
        if len(years) < 2:
            continue
        if not CAUSE_AFTER.search(sentence):
            continue
        if not BUILT.search(sentence):
            continue
        earliest, latest = min(years), max(years)
        if earliest < latest and CAUSE_AFTER.search(sentence):
            # "after 1773" + "founded 1767" in one causal sentence.
            after_years = [
                int(match.group(1))
                for match in YEAR.finditer(sentence)
                if CAUSE_AFTER.search(sentence[: match.start() + 1][-40:])
            ]
            built_years = [
                int(match.group(1))
                for match in YEAR.finditer(sentence)
                if BUILT.search(sentence[max(0, match.start() - 40) : match.start() + 1])
            ]
            for cause_year in after_years or [latest]:
                for built_year in built_years or [earliest]:
                    if built_year < cause_year:
                        issues.append(
                            "chronology_conflict: construction/founding "
                            f"{built_year} cannot be caused by later {cause_year}"
                        )
    return list(dict.fromkeys(issues))


def venue_framing_issues(text: str) -> list[str]:
    if VENUE_MISUSE.search(text or ""):
        return ["unsuitable_venue: religious/cultural site framed as a warming room"]
    return []


def unverified_hours_issues(text: str) -> list[str]:
    if HOURS_WITHOUT_ASOF.search(text or "") and not ASOF.search(text or ""):
        return ["unsupported_claim: precise opening hours without a verification date"]
    return []


__all__ = [
    "chronology_conflicts",
    "unverified_hours_issues",
    "venue_framing_issues",
]
