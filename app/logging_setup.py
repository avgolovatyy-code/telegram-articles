"""Structured logging.

Every job-level log line carries the fields required by the specification:
job_id, article_id, topic_id, market, entity_type, entity_id, operation, model,
cost_usd, duration_ms, status, error.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    for noisy in ("httpx", "httpcore", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    renderer: Any
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    # Imported here: redaction reads the settings' secret names, and importing it at
    # module scope would make logging depend on configuration import order.
    from app.security.redaction import redaction_processor

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            redaction_processor,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)


def new_job_id(prefix: str = "job") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@contextmanager
def job_context(operation: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Bind job-scoped fields and emit a start/finish pair with duration and status."""
    job_id = fields.pop("job_id", None) or new_job_id()
    log = get_logger("job")
    bound = {
        "job_id": job_id,
        "operation": operation,
        **{k: v for k, v in fields.items() if v is not None},
    }
    structlog.contextvars.bind_contextvars(**bound)
    started = time.monotonic()
    result: dict[str, Any] = {"job_id": job_id, "status": "ok"}
    log.info("job.start")
    try:
        yield result
    except Exception as exc:
        result["status"] = "error"
        log.error(
            "job.finish",
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise
    else:
        log.info(
            "job.finish",
            status=result.get("status", "ok"),
            duration_ms=int((time.monotonic() - started) * 1000),
            **{k: v for k, v in result.items() if k not in {"job_id", "status"}},
        )
    finally:
        structlog.contextvars.unbind_contextvars(*bound.keys())


__all__ = ["configure_logging", "get_logger", "job_context", "new_job_id"]
