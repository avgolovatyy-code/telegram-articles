"""Grammatical case handling for query patterns.

Russian query patterns cannot simply interpolate a nominative entity name: «что
посмотреть в Париж» is wrong, «что посмотреть в Париже» is right. Patterns therefore
declare the case they need (``{entity:loct}``) and this module inflects the name.

English patterns use ``{entity}`` and are passed through untouched.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.logging_setup import get_logger

log = get_logger("topics.morphology")

#: pymorphy3 grammeme names supported in patterns.
CASES = {"nomn", "gent", "datv", "accs", "ablt", "loct"}

_PLACEHOLDER_RE = re.compile(r"\{(?P<name>[a-z_]+)(?::(?P<case>[a-z]+))?\}")
#: Whitespace only: pymorphy3 declines hyphenated toponyms ("Санкт-Петербург") as
#: single words, and splitting them produces "Санкте-Петербурге".
_TOKEN_SPLIT_RE = re.compile(r"(\s+)")


@lru_cache(maxsize=1)
def _analyzer() -> Any | None:
    try:
        import pymorphy3
    except ImportError:  # pragma: no cover - optional dependency guard
        log.warning("morphology.pymorphy3_missing")
        return None
    try:
        return pymorphy3.MorphAnalyzer()
    except Exception as exc:  # pragma: no cover - dictionary load failure
        log.warning("morphology.analyzer_failed", error=str(exc))
        return None


def _match_capitalisation(source: str, inflected: str) -> str:
    """Restore the source casing, segment by segment for hyphenated toponyms.

    pymorphy3 lowercases everything, so "Ростов-на-Дону" comes back as
    "ростове-на-дону" and has to be re-cased against the original.
    """
    source_parts = source.split("-")
    inflected_parts = inflected.split("-")
    if len(source_parts) == len(inflected_parts) and len(source_parts) > 1:
        pairs = zip(source_parts, inflected_parts, strict=True)
        return "-".join(_match_word_case(src, out) for src, out in pairs)
    return _match_word_case(source, inflected)


def _match_word_case(source: str, inflected: str) -> str:
    if source.isupper():
        return inflected.upper()
    if source[:1].isupper():
        return inflected[:1].upper() + inflected[1:]
    return inflected


@lru_cache(maxsize=4096)
def inflect_ru(phrase: str, case: str) -> str:
    """Inflect a Russian phrase into ``case``; return it unchanged when impossible."""
    if case == "nomn" or case not in CASES:
        return phrase
    analyzer = _analyzer()
    if analyzer is None:
        return phrase

    parts = _TOKEN_SPLIT_RE.split(phrase)
    out: list[str] = []
    changed = False
    for part in parts:
        if not part or _TOKEN_SPLIT_RE.fullmatch(part) or not any(ch.isalpha() for ch in part):
            out.append(part)
            continue
        if not _is_cyrillic(part):
            out.append(part)
            continue
        try:
            parsed = analyzer.parse(part)
        except Exception:  # pragma: no cover - defensive
            out.append(part)
            continue
        inflected = None
        for candidate in parsed[:3]:
            form = candidate.inflect({case})
            if form is not None:
                inflected = form.word
                break
        if inflected is None:
            out.append(part)
            continue
        out.append(_match_capitalisation(part, inflected))
        changed = True
    return "".join(out) if changed else phrase


def _is_cyrillic(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    cyrillic = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
    return cyrillic / len(letters) > 0.6


def render_pattern(pattern: str, values: dict[str, str], *, market: str) -> str:
    """Fill ``{placeholder}`` / ``{placeholder:case}`` slots in a query pattern."""

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        case = match.group("case")
        value = values.get(name)
        if value is None:
            return match.group(0)
        if market == "ru" and case:
            return inflect_ru(value, case)
        return value

    rendered = _PLACEHOLDER_RE.sub(replace, pattern)
    return re.sub(r"\s+", " ", rendered).strip()


def pattern_placeholders(pattern: str) -> set[str]:
    return {match.group("name") for match in _PLACEHOLDER_RE.finditer(pattern)}


__all__ = ["CASES", "inflect_ru", "pattern_placeholders", "render_pattern"]
