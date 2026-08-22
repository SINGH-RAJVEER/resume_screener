"""add embedding storage

Revision ID: b41c7e2d9a55
Revises: f1c9b92d5e04
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "b41c7e2d9a55"
down_revision: str | None = "f1c9b92d5e04"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"resume_block_embedding",
		sa.Column("resume_version_id", sa.Text(), sa.ForeignKey("resume_version.id", ondelete="CASCADE"), nullable=False),
		sa.Column("block_id", sa.Text(), nullable=False),
		sa.Column("model", sa.Text(), nullable=False),
		sa.Column("text_hash", sa.Text(), nullable=False),
		sa.Column("vector", JSONB(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
		sa.PrimaryKeyConstraint("resume_version_id", "block_id", "model", name="pk_resume_block_embedding"),
	)
	op.create_table(
		"embedding_cache",
		sa.Column("model", sa.Text(), nullable=False),
		sa.Column("text_hash", sa.Text(), nullable=False),
		sa.Column("vector", JSONB(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
		sa.PrimaryKeyConstraint("model", "text_hash", name="pk_embedding_cache"),
	)


def downgrade() -> None:
	op.drop_table("embedding_cache")
	op.drop_table("resume_block_embedding")
