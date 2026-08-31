"""FastAPI application: admin UI, click tracking and health endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.admin.routes import router as admin_router
from app.api.routes import router as api_router
from app.api.slack_routes import router as slack_router
from app.config import get_settings
from app.errors import EngineError
from app.generation.covers import GENERATED_DIR
from app.logging_setup import configure_logging, get_logger
from app.scheduler.runner import SchedulerRunner

log = get_logger("app")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    runner: SchedulerRunner | None = None
    if settings.scheduler_enabled:
        runner = SchedulerRunner()
        runner.start()
        application.state.scheduler = runner
        log.info("scheduler.started")
    try:
        yield
    finally:
        if runner is not None:
            runner.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    application = FastAPI(
        title="WeGoTrip Telegram Content Engine",
        version="0.1.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    @application.exception_handler(EngineError)
    async def _engine_error_handler(_request, exc: EngineError):
        log.warning("request.engine_error", error=str(exc), type=type(exc).__name__)
        return JSONResponse(
            status_code=502 if getattr(exc, "retryable", False) else 400,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    @application.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(api_router)
    application.include_router(slack_router)
    application.include_router(admin_router)

    static_dir = Path(__file__).parent / "admin" / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Generated covers are written to disk and served from here so Telegram can fetch
    # them by URL. The directory only exists when ALLOW_GENERATED_COVERS is enabled.
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/media/generated",
        StaticFiles(directory=str(GENERATED_DIR)),
        name="generated-media",
    )

    return application


app = create_app()

__all__ = ["app", "create_app"]
