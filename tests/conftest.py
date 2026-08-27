from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

# The test profile is pinned rather than inherited: the suite asserts on concrete
# budgets, windows and thresholds, so an exported variable in the developer's shell
# (or a stray .env) must not change the outcome.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["CATALOG_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TELEGRAM_DRY_RUN"] = "true"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_EN_CHANNEL"] = "@wegotrip"
os.environ["TELEGRAM_RU_CHANNEL"] = "@wegotrip_ru"
os.environ["TELEGRAM_TEST_CHANNEL"] = "@wegotrip_test"
os.environ["VALIDATE_MEDIA_OVER_NETWORK"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TRACKING_BASE_URL"] = "https://engine.example"
os.environ["DAILY_AI_BUDGET_USD"] = "3.00"
os.environ["EN_ARTICLES_MIN_PER_DAY"] = "10"
os.environ["RU_ARTICLES_MIN_PER_DAY"] = "10"
os.environ["EN_ARTICLES_MAX_PER_DAY"] = "0"
os.environ["RU_ARTICLES_MAX_PER_DAY"] = "0"
os.environ["EN_PUBLISH_PER_DAY"] = "0"
os.environ["RU_PUBLISH_PER_DAY"] = "0"
os.environ["PUBLISH_TIMEZONE"] = "Europe/Moscow"
os.environ["PUBLISH_WINDOW_START_HOUR"] = "10"
os.environ["PUBLISH_WINDOW_END_HOUR"] = "21"
os.environ["MIN_POST_INTERVAL_MINUTES"] = "20"
os.environ["MIN_TOPIC_SCORE"] = "0.25"
os.environ["ALLOW_GENERATED_COVERS"] = "false"
os.environ["AUTO_PUBLISH_EN"] = "false"
os.environ["AUTO_PUBLISH_RU"] = "false"

from app.config import Settings, reload_settings
from app.db import models  # noqa: F401
from app.db.base import Base, configure_engine, get_session_factory


@pytest.fixture(scope="session")
def settings() -> Settings:
    return reload_settings()


@pytest.fixture()
def session(settings: Settings) -> Iterator[Session]:
    engine = configure_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.rollback()
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def mock_catalog():
    from app.catalog.mock import MockCatalogProvider

    return MockCatalogProvider()


@pytest.fixture()
def synced_session(session: Session, mock_catalog, settings: Settings) -> Session:
    """A session with the EN and RU fixture catalogues loaded and seeds applied."""
    from app.catalog.sync import CatalogSyncService
    from app.scheduler.jobs import seed_reference_data

    seed_reference_data(session, settings)
    service = CatalogSyncService(session, mock_catalog, settings=settings)
    for market in ("en", "ru"):
        service.sync_market(market)
    session.flush()
    return session
