"""Media candidates offered to the writer and consumed by the renderer.

Lives outside both packages so ``app.generation`` and ``app.telegram`` can share it
without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MediaCandidate:
    """One WeGoTrip-sourced asset an article is allowed to place."""

    id: str
    url: str
    kind: str
    source_entity_type: str
    source_entity_id: str | None = None
    product_external_id: str | None = None
    caption: str | None = None
    role: str = "inline"

    def as_context(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "belongs_to": self.source_entity_type,
            "caption": self.caption,
        }


__all__ = ["MediaCandidate"]
