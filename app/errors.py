"""Domain error hierarchy.

Errors are split into `retryable` and terminal so that job runners can decide
whether re-running the job can help.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base error for everything raised by the content engine."""

    retryable = False


class ConfigurationError(EngineError):
    """A required setting is missing or invalid."""


class UpstreamError(EngineError):
    """An external dependency failed."""

    retryable = True

    def __init__(self, message: str, *, status_code: int | None = None, payload: object = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class CatalogError(UpstreamError):
    """WeGoTrip Affiliate API failure."""


class CatalogSchemaError(CatalogError):
    """The WeGoTrip payload no longer matches the expected shape."""

    retryable = False


class LLMError(UpstreamError):
    """OpenAI (or another LLM provider) failure."""


class LLMOutputError(LLMError):
    """The model returned malformed or schema-violating output."""

    retryable = True


class TelegramError(UpstreamError):
    """Telegram Bot API failure."""


class TelegramRateLimited(TelegramError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class TelegramValidationError(TelegramError):
    """Telegram rejected the payload; retrying the same payload will not help."""

    retryable = False


class BudgetExceeded(EngineError):
    """The projected cost of an operation would break the daily hard cap."""

    def __init__(self, message: str, *, remaining_usd: float, projected_usd: float):
        super().__init__(message)
        self.remaining_usd = remaining_usd
        self.projected_usd = projected_usd


class ValidationFailed(EngineError):
    """An article failed a quality/factual/technical gate."""

    def __init__(self, message: str, *, issues: list[str] | None = None):
        super().__init__(message)
        self.issues = issues or []


class MediaValidationError(EngineError):
    """A media asset cannot be published."""


class DuplicatePublication(EngineError):
    """The idempotency guard refused a second publication of the same article."""


__all__ = [
    "BudgetExceeded",
    "CatalogError",
    "CatalogSchemaError",
    "ConfigurationError",
    "DuplicatePublication",
    "EngineError",
    "LLMError",
    "LLMOutputError",
    "MediaValidationError",
    "TelegramError",
    "TelegramRateLimited",
    "TelegramValidationError",
    "UpstreamError",
    "ValidationFailed",
]
