from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("CATALOG_PROVIDER", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("TELEGRAM_DRY_RUN", "true")
os.environ.setdefault("TELEGRAM_TEST_CHANNEL", "@wegotrip_test")
os.environ.setdefault("VALIDATE_MEDIA_OVER_NETWORK", "false")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("TRACKING_BASE_URL", "https://engine.example")

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
