"""dzen publishing kits and weekday slack handoff

Revision ID: d1e2f3a4b5c6
Revises: c8f9a0b1d2e3
Create Date: 2026-11-18 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

import app.db.types

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c8f9a0b1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "dzen_articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("format", sa.String(length=48), nullable=False),
        sa.Column("pillar", sa.String(length=48), nullable=False),
        sa.Column("audience", sa.String(length=48), nullable=False),
        sa.Column("planned_date", sa.Date()),
        sa.Column("destination_country", sa.String(length=16)),
        sa.Column("destination_city", sa.String(length=128)),
        sa.Column("headline", sa.Text()),
        sa.Column("lead", sa.Text()),
        sa.Column("body_ast", _JSON, nullable=False, server_default="{}"),
        sa.Column("claim_ledger", _JSON, nullable=False, server_default="[]"),
        sa.Column("brief", _JSON, nullable=False, server_default="{}"),
        sa.Column("product_ids", _JSON, nullable=False, server_default="[]"),
        sa.Column("media_manifest", _JSON, nullable=False, server_default="[]"),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("superseded_by_id", sa.Integer()),
        sa.Column("quality_scores", _JSON, nullable=False, server_default="{}"),
        sa.Column("actual_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("writer_model", sa.String(length=64)),
        sa.Column("critic_model", sa.String(length=64)),
        sa.Column("ready_at", app.db.types.UTCDateTime()),
        sa.Column("handed_off_at", app.db.types.UTCDateTime()),
        sa.Column("published_url", sa.Text()),
        sa.Column("published_confirmed_at", app.db.types.UTCDateTime()),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_dzen_articles_public_id", "dzen_articles", ["public_id"])
    op.create_index("ix_dzen_articles_status", "dzen_articles", ["status"])
    op.create_index("ix_dzen_articles_status_planned", "dzen_articles", ["status", "planned_date"])
    op.create_index("ix_dzen_articles_content_hash", "dzen_articles", ["content_hash"])

    op.create_table(
        "dzen_publishing_kits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("article_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("render_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("access_token", sa.String(length=64), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("plain_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("cover_url", sa.Text()),
        sa.Column("cover_asset_id", sa.String(length=64)),
        sa.Column("media_manifest_json", _JSON, nullable=False, server_default="[]"),
        sa.Column("product_links_json", _JSON, nullable=False, server_default="[]"),
        sa.Column("zip_asset_path", sa.Text()),
        sa.Column("zip_sha256", sa.String(length=64)),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ready_at", app.db.types.UTCDateTime()),
        sa.Column("expires_at", app.db.types.UTCDateTime()),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["dzen_articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("access_token"),
    )
    op.create_index("ix_dzen_kits_article_id", "dzen_publishing_kits", ["article_id"])
    op.create_index(
        "ix_dzen_kits_article_version",
        "dzen_publishing_kits",
        ["article_id", "article_version"],
    )

    op.create_table(
        "dzen_handoff_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("local_work_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("slack_channel_id", sa.String(length=32), nullable=False),
        sa.Column("staff_user_id", sa.String(length=32), nullable=False),
        sa.Column("slack_message_ts", sa.String(length=32)),
        sa.Column("slack_thread_ts", sa.String(length=32)),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("sent_at", app.db.types.UTCDateTime()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint(
            "slack_channel_id",
            "staff_user_id",
            "local_work_date",
            name="uq_dzen_handoff_day",
        ),
    )
    op.create_index("ix_dzen_handoff_batches_date", "dzen_handoff_batches", ["local_work_date"])

    op.create_table(
        "dzen_handoff_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("article_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="handed_off"),
        sa.Column("published_url", sa.Text()),
        sa.Column("confirmed_by", sa.String(length=64)),
        sa.Column("confirmed_at", app.db.types.UTCDateTime()),
        sa.Column("verified_at", app.db.types.UTCDateTime()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", app.db.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.types.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["dzen_handoff_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["dzen_articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id", "article_id", "article_version", name="uq_dzen_handoff_item"
        ),
    )
    op.create_index("ix_dzen_handoff_items_batch", "dzen_handoff_items", ["batch_id"])
    op.create_index("ix_dzen_handoff_items_article", "dzen_handoff_items", ["article_id"])


def downgrade() -> None:
    op.drop_table("dzen_handoff_items")
    op.drop_table("dzen_handoff_batches")
    op.drop_table("dzen_publishing_kits")
    op.drop_table("dzen_articles")
