"""Shared column types.

JSONB is used on PostgreSQL (the production target) and plain JSON on SQLite so
that the same models can be exercised in tests without a database server.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

JSONColumn = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator):
    """Timezone-aware datetime that always round-trips as UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


__all__ = ["JSONColumn", "UTCDateTime", "utcnow"]
