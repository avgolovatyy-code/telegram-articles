"""OpenAI Responses API provider.

Uses the HTTP API directly (``POST /v1/responses``) rather than the SDK so the exact
request shape, retry policy and usage accounting stay visible.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from app.ai.provider import Citation, LLMRequest, LLMResponse, Usage
from app.catalog.http import request_with_retries
from app.config import Settings, get_settings
from app.errors import ConfigurationError, LLMError, LLMOutputError
from app.logging_setup import get_logger

log = get_logger("ai.openai")


class OpenAIProvider:
    name = "openai"

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self._settings = settings or get_settings()
        if not self._settings.openai_api_key:
            raise ConfigurationError("OPENAI_API_KEY is not set")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(self._settings.openai_timeout_seconds),
            base_url=self._settings.openai_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {self._settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------- responses
    def complete(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "instructions": request.instructions,
            "input": request.input,
        }
        if request.json_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "schema": request.json_schema,
                    "strict": True,
                }
            }
        if request.max_output_tokens:
            payload["max_output_tokens"] = request.max_output_tokens
        if request.reasoning_effort:
            payload["reasoning"] = {"effort": request.reasoning_effort}
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.enable_web_search:
            payload["tools"] = [{"type": "web_search"}]
            payload["include"] = ["web_search_call.action.sources"]
        if request.metadata:
            payload["metadata"] = request.metadata

        started = time.monotonic()
        response = request_with_retries(
            self._client,
            "POST",
            "/responses",
            json=payload,
            max_retries=self._settings.openai_max_retries,
            error_cls=LLMError,
        )
        duration_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 400:
            raise LLMError(
                f"OpenAI responded {response.status_code}",
                status_code=response.status_code,
                payload=response.text[:800],
            )

        body = response.json()
        text = _extract_text(body)
        usage = _extract_usage(body)
        citations = _extract_citations(body)

        parsed = None
        if request.json_schema is not None:
            parsed = _parse_json(text)

        return LLMResponse(
            text=text,
            parsed=parsed,
            model=body.get("model", request.model),
            usage=usage,
            citations=citations,
            duration_ms=duration_ms,
            raw=body,
        )

    # ----------------------------------------------------------------- images
    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> bytes | None:
        response = request_with_retries(
            self._client,
            "POST",
            "/images/generations",
            json={
                "model": self._settings.openai_image_model,
                "prompt": prompt,
                "size": size,
                "n": 1,
            },
            max_retries=1,
            error_cls=LLMError,
        )
        if response.status_code >= 400:
            log.warning(
                "openai.image_failed", status=response.status_code, body=response.text[:300]
            )
            return None
        data = response.json().get("data") or []
        if not data:
            return None
        encoded = data[0].get("b64_json")
        if encoded:
            return base64.b64decode(encoded)
        url = data[0].get("url")
        if not url:
            return None
        image = self._client.get(url)
        return image.content if image.status_code < 400 else None


def _extract_text(body: dict[str, Any]) -> str:
    direct = body.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in body.get("output", []) or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []) or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                chunks.append(str(part.get("text", "")))
    return "".join(chunks)


def _extract_usage(body: dict[str, Any]) -> Usage:
    raw = body.get("usage") or {}
    input_details = raw.get("input_tokens_details") or {}
    output_details = raw.get("output_tokens_details") or {}
    tool_calls = 0
    web_search_calls = 0
    for item in body.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", ""))
        if item_type.endswith("_call"):
            tool_calls += 1
        if item_type == "web_search_call":
            web_search_calls += 1
    return Usage(
        input_tokens=int(raw.get("input_tokens") or 0),
        cached_input_tokens=int(input_details.get("cached_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or 0),
        reasoning_tokens=int(output_details.get("reasoning_tokens") or 0),
        tool_calls=tool_calls,
        web_search_calls=web_search_calls,
    )


def _extract_citations(body: dict[str, Any]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()

    def add(url: Any, title: Any = None, snippet: Any = None) -> None:
        if not isinstance(url, str) or not url.startswith("http") or url in seen:
            return
        seen.add(url)
        citations.append(
            Citation(
                url=url,
                title=title if isinstance(title, str) else None,
                snippet=snippet if isinstance(snippet, str) else None,
            )
        )

    for item in body.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content", []) or []:
            if not isinstance(part, dict):
                continue
            for annotation in part.get("annotations", []) or []:
                if isinstance(annotation, dict) and annotation.get("type") == "url_citation":
                    add(annotation.get("url"), annotation.get("title"))
        action = item.get("action")
        if isinstance(action, dict):
            for source in action.get("sources", []) or []:
                if isinstance(source, dict):
                    add(source.get("url"), source.get("title"))
    return citations


def _parse_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.rsplit("```", 1)[0]
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LLMOutputError(f"Model returned malformed JSON: {exc}") from exc


__all__ = ["OpenAIProvider"]
