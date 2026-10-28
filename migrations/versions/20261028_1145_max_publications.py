"""max publications table

Revision ID: a1b2c3d4e5f6
Revises: d710898bd9ec
Create Date: 2026-10-28 11:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

import app.db.types

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "d710898bd9ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "max_publications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("target", sa.String(length=16), nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=True),
        sa.Column("channel_ref", sa.String(length=128), nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=True),
        sa.Column("message_url", sa.Text(), nullable=True),
        sa.Column("article_version", sa.Integer(), nullable=True),
        sa.Column("audience_country", sa.String(length=8), nullable=False),
        sa.Column("benefit", sa.String(length=64), nullable=True),
        sa.Column("domestic_or_outbound", sa.String(length=16), nullable=True),
        sa.Column("skip_reason", sa.String(length=128), nullable=True),
        sa.Column("skipped", sa.Boolean(), nullable=False),
        sa.Column("adaptation", _JSON, nullable=True),
        sa.Column("max_response", _JSON, nullable=True),
        sa.Column("published_at", app.db.types.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_max_publication_idempotency"),
    )
    op.create_index(
        "ix_max_publications_article_id", "max_publications", ["article_id"], unique=False
    )
    op.create_index(
        "ix_max_publications_published_at", "max_publications", ["published_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_max_publications_published_at", table_name="max_publications")
    op.drop_index("ix_max_publications_article_id", table_name="max_publications")
    op.drop_table("max_publications")
