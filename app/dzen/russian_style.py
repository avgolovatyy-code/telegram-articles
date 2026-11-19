"""High-confidence checks for translated or editorial-sounding Russian copy."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RussianStyleIssue:
    span: str
    explanation: str
    proposed_fix: str


@dataclass(frozen=True, slots=True)
class _StyleRule:
    pattern: re.Pattern[str]
    explanation: str
    proposed_fix: str


def _rule(pattern: str, explanation: str, proposed_fix: str) -> _StyleRule:
    return _StyleRule(re.compile(pattern, re.IGNORECASE), explanation, proposed_fix)


# These are deliberately narrow. A language model remains responsible for nuance;
# this list only blocks constructions that are reliably unnatural in travel copy.
_RULES = (
    _rule(
        r"\b(?:это|получаются?)\s+(?:две|три|четыре)\s+(?:разн\w+\s+)?скорост\w*",
        "literal translation: places are described as abstract «speeds»",
        "State the practical difference: one place needs a slow walk, another is a short stop.",
    ),
    _rule(
        r"\bсобра(?:ть|ны?|на)\b[^.!?\n]{0,70}\bв\s+одну\s+линию\b",
        "editorial planning jargon leaked into reader-facing copy",
        "Describe the route directly: where to start, where to go next, and where to finish.",
    ),
    _rule(
        r"\bдерж(?:ит|ат)\s+(?:купеческ\w+\s+масштаб|линию|ритм|"
        r"витрины|ночной\s+свет|парк|музеи|мастерские)\b",
        "unnatural calque with «держит» and an inanimate subject",
        "Use a concrete verb such as «сохранился», «находится», «видно» or «идите».",
    ),
    _rule(
        r"\b(?:ед[уаы]|кухн\w*)\b[^.!?\n]{0,55}\bдержите\b",
        "editorial command about food sounds translated",
        "Recommend a dish or café stop in ordinary Russian without instructing "
        "the reader to «hold» it.",
    ),
    _rule(
        r"\b(?:мечет\w*|дом\w*|музе\w*|квартал\w*)\s+"
        r"(?:сидит|сидят)\s+[^.!?\n]{0,45}\bткан\w*",
        "literal spatial metaphor: buildings «sit in the urban fabric»",
        "Say that the buildings stand among homes or form part of an ordinary residential quarter.",
    ),
    _rule(
        r"\bбез\s+экзамена\b",
        "opaque metaphor that does not give the reader useful advice",
        "Say explicitly that there is no need to order many dishes or prove "
        "knowledge of the cuisine.",
    ),
    _rule(
        r"\b(?:коротк\w+\s+)?слой\s+(?:внутри\s+дня|прогулки|маршрута|дня)\b",
        "abstract editorial metaphor «слой»",
        "Explain how many hours the activity takes and what remains outside it.",
    ),
    _rule(
        r"\b(?:друг\w+|спокойн\w+)\s+географ\w*\b",
        "abstract geography metaphor instead of a route",
        "Name the neighbourhood or riverbank and explain how to get there.",
    ),
    _rule(
        r"\b(?:друг\w+\s+шаг|меня\w+\s+скорост\w*|друг\w+\s+скорост\w*)\b",
        "literal translation about a place changing the reader's «step» or «speed»",
        "Describe the actual pace, distance, terrain or crowd level.",
    ),
    _rule(
        r"\b(?:схлоп\w*|закрыть)\b[^.!?\n]{0,55}\b(?:город|центр|кремл|маршрут|круг)\w*",
        "production jargon used as travel advice",
        "Say «попытаться обойти», «успеть посмотреть» or name the exact route.",
    ),
    _rule(
        r"\b(?:читается\s+как|зада[её]т\s+масштаб|да[её]т\s+масштаб|"
        r"возраст\s+(?:городской\s+)?ткани|плотн\w+\s+ось)\b",
        "abstract translated phrasing hides the concrete observation",
        "Replace it with a visible fact about the street, building, distance or neighbourhood.",
    ),
)


def russian_style_issues(text: str) -> list[RussianStyleIssue]:
    issues: list[RussianStyleIssue] = []
    seen: set[tuple[str, str]] = set()
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            span = match.group(0).strip()
            key = (span.casefold(), rule.explanation)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                RussianStyleIssue(
                    span=span,
                    explanation=rule.explanation,
                    proposed_fix=rule.proposed_fix,
                )
            )
    return issues


__all__ = ["RussianStyleIssue", "russian_style_issues"]
