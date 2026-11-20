"""Semantic repetition across sections — not exact-string matching of one city's advice."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.dzen.schemas import DzenArticleAST


def _body(ast: DzenArticleAST) -> str:
    parts = [ast.headline, ast.lead, ast.practical_takeaway]
    for block in ast.blocks:
        if block.text:
            parts.append(block.text)
        parts.extend(block.items)
    return "\n".join(parts)


WORD = re.compile(r"[A-Za-zА-Яа-яЁё]{4,}")
STOP = {
    "этот",
    "этого",
    "после",
    "перед",
    "можно",
    "нужно",
    "если",
    "когда",
    "также",
    "очень",
    "просто",
    "город",
    "места",
    "маршрут",
    "время",
    "лучше",
    "стоит",
    "читател",
}


@dataclass(slots=True)
class SemanticRedundancyReport:
    repeats: list[tuple[str, int]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def _tokens(text: str) -> set[str]:
    found: set[str] = set()
    for raw in WORD.findall(text.casefold().replace("ё", "е")):
        if raw in STOP or len(raw) < 5:
            continue
        found.add(raw)
    return found


def _sections(ast: DzenArticleAST) -> list[str]:
    chunks = [ast.lead or ""]
    buf: list[str] = []
    for block in ast.blocks:
        if block.type == "heading":
            if buf:
                chunks.append(" ".join(buf))
                buf = []
            continue
        if block.text:
            buf.append(block.text)
        buf.extend(block.items)
    if buf:
        chunks.append(" ".join(buf))
    if ast.practical_takeaway:
        chunks.append(ast.practical_takeaway)
    return [chunk for chunk in chunks if len(chunk) > 80]


def redundancy_report(ast: DzenArticleAST) -> SemanticRedundancyReport:
    report = SemanticRedundancyReport()
    sections = _sections(ast)
    fingerprints = [_tokens(chunk) for chunk in sections]
    for i, left in enumerate(fingerprints):
        if len(left) < 8:
            continue
        hits = 1
        for j, right in enumerate(fingerprints):
            if i == j or len(right) < 8:
                continue
            overlap = left & right
            if len(overlap) / max(len(left), 1) >= 0.85:
                hits += 1
        if hits >= 3:
            sample = " ".join(sorted(left)[:6])
            report.repeats.append((sample, hits))
    # Same 12-word window in three different sections — not a dense unique list.
    section_windows: list[set[str]] = []
    for chunk in sections:
        words = WORD.findall(chunk.casefold())
        found: set[str] = set()
        for index in range(0, max(0, len(words) - 11)):
            found.add(" ".join(words[index : index + 12]))
        section_windows.append(found)
    shared = 0
    if len(section_windows) >= 3:
        counts: dict[str, int] = {}
        for found in section_windows:
            for window in found:
                counts[window] = counts.get(window, 0) + 1
        shared = sum(1 for count in counts.values() if count >= 3)
    numbered = re.findall(r"слой\s+\d+", _body(ast).casefold())
    if len(numbered) >= 3:
        report.issues.append("repetition: numbered filler layers restating the same places")
    if report.repeats or shared:
        report.issues.append("repetition: the same idea is restated in several sections")
    return report


__all__ = ["SemanticRedundancyReport", "redundancy_report"]
