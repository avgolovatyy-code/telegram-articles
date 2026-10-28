"""editorial v2.2 runs, plan slots, branding history

Revision ID: b7e8f9a0c1d2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-28 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

import app.db.types

revision: str = "b7e8f9a0c1d2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "editorial_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("editorial_thesis", sa.Text(), nullable=True),
        sa.Column("daily_summary", sa.Text(), nullable=True),
        sa.Column("brief", _JSON, nullable=False),
        sa.Column("decisions", _JSON, nullable=False),
        sa.Column("diff", _JSON, nullable=False),
        sa.Column("llm_run_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("applied_at", app.db.types.UTCDateTime(), nullable=True),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_editorial_runs_market_date", "editorial_runs", ["market", "run_date"])

    op.create_table(
        "editorial_plan_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=True),
        sa.Column("pillar", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("angle", sa.Text(), nullable=True),
        sa.Column("reader_value", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("needs_human_review", sa.Boolean(), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["editorial_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_candidates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_editorial_slots_market_date", "editorial_plan_slots", ["market", "slot_date"]
    )
    op.create_index(
        "ix_editorial_slots_market_status", "editorial_plan_slots", ["market", "status"]
    )

    op.create_table(
        "editorial_preference_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_editorial_preference_log_market", "editorial_preference_log", ["market"])

    op.create_table(
        "channel_branding_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("branding_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("before", _JSON, nullable=False),
        sa.Column("after", _JSON, nullable=False),
        sa.Column("steps", _JSON, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("applied_at", app.db.types.UTCDateTime(), nullable=True),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_channel_branding_history_market", "channel_branding_history", ["market"])


def downgrade() -> None:
    op.drop_index("ix_channel_branding_history_market", table_name="channel_branding_history")
    op.drop_table("channel_branding_history")
    op.drop_index("ix_editorial_preference_log_market", table_name="editorial_preference_log")
    op.drop_table("editorial_preference_log")
    op.drop_index("ix_editorial_slots_market_status", table_name="editorial_plan_slots")
    op.drop_index("ix_editorial_slots_market_date", table_name="editorial_plan_slots")
    op.drop_table("editorial_plan_slots")
    op.drop_index("ix_editorial_runs_market_date", table_name="editorial_runs")
    op.drop_table("editorial_runs")
