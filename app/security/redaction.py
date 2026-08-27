"""Secret redaction for logs.

A leaked credential is usually leaked by an exception message or a debug line, not by
the code that legitimately uses it. This processor replaces any known secret value in
rendered log output with ``***`` and also masks anything that *looks* like a credential,
so an unregistered key still does not reach the log.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

from app.security.names import SECRET_NAMES

MASK = "***"

#: Shapes of well-known credentials, masked even when we never stored them.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),  # OpenAI
    re.compile(r"xox[abposr]-[A-Za-z0-9\-]{10,}"),  # Slack
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_\-]{30,}\b"),  # Telegram bot token
    re.compile(r"dop_v1_[a-f0-9]{64}"),  # DigitalOcean
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
)

#: Values short enough to appear by coincidence are not worth substring-matching on.
_MIN_LITERAL_LENGTH = 8


def known_secret_values() -> list[str]:
    values = []
    for name in SECRET_NAMES:
        value = os.environ.get(name)
        if value and len(value) >= _MIN_LITERAL_LENGTH:
            values.append(value)
    # Longest first so a value containing another is masked whole.
    return sorted(set(values), key=len, reverse=True)


def redact(text: str, extra_values: list[str] | None = None) -> str:
    if not text:
        return text
    for value in [*(extra_values or []), *known_secret_values()]:
        if value in text:
            text = text.replace(value, MASK)
    for pattern in _PATTERNS:
        text = pattern.sub(MASK, text)
    return text


def _redact_any(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {key: _redact_any(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_any(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_any(item, secrets) for item in value)
    return value


def redaction_processor(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """structlog processor: mask credentials anywhere in the event."""
    secrets = known_secret_values()
    if not secrets and not event_dict:
        return event_dict
    return {key: _redact_any(value, secrets) for key, value in event_dict.items()}


__all__ = ["MASK", "known_secret_values", "redact", "redaction_processor"]
