"""LLM provider abstraction.

The engine talks to :class:`LLMProvider`, never to a specific vendor SDK. Swapping or
renaming a model is a configuration change; swapping the vendor means adding one class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    tool_calls: int = 0
    web_search_calls: int = 0

    def merge(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            tool_calls=self.tool_calls + other.tool_calls,
            web_search_calls=self.web_search_calls + other.web_search_calls,
        )


@dataclass(slots=True)
class Citation:
    url: str
    title: str | None = None
    snippet: str | None = None


@dataclass(slots=True)
class LLMResponse:
    text: str
    parsed: Any | None
    model: str
    usage: Usage
    citations: list[Citation] = field(default_factory=list)
    duration_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMRequest:
    """One structured call to a model."""

    model: str
    instructions: str
    input: str
    json_schema: dict[str, Any] | None = None
    schema_name: str = "response"
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None
    enable_web_search: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...

    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> bytes | None: ...


__all__ = ["Citation", "LLMProvider", "LLMRequest", "LLMResponse", "Usage"]
