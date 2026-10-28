"""editorial v3.0: RU demand observations + slot mechanics

Revision ID: c8f9a0b1d2e3
Revises: b7e8f9a0c1d2
Create Date: 2026-10-28 22:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

import app.db.types

revision: str = "c8f9a0b1d2e3"
down_revision: str | None = "b7e8f9a0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.add_column("editorial_plan_slots", sa.Column("editorial_mechanic", sa.String(length=64)))
    op.add_column("editorial_plan_slots", sa.Column("audience_axis", sa.String(length=64)))
    op.add_column("editorial_plan_slots", sa.Column("destination_country", sa.String(length=16)))
    op.add_column("editorial_plan_slots", sa.Column("destination_city", sa.String(length=128)))
    op.add_column(
        "editorial_plan_slots",
        sa.Column("channel_targets", _JSON, nullable=False, server_default="[]"),
    )
    op.create_table(
        "russia_demand_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("geo", sa.String(length=64), nullable=False),
        sa.Column("audience_origin", sa.String(length=16), nullable=False),
        sa.Column("travel_type", sa.String(length=32), nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("segment", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("sample_context", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("caveat", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ru_demand_geo_metric_period",
        "russia_demand_observations",
        ["geo", "metric_type", "segment", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_ru_demand_geo_metric_period", table_name="russia_demand_observations")
    op.drop_table("russia_demand_observations")
    op.drop_column("editorial_plan_slots", "channel_targets")
    op.drop_column("editorial_plan_slots", "destination_city")
    op.drop_column("editorial_plan_slots", "destination_country")
    op.drop_column("editorial_plan_slots", "audience_axis")
    op.drop_column("editorial_plan_slots", "editorial_mechanic")
