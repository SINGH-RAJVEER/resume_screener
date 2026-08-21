"""add independent evaluations

Revision ID: 835f239aa101
Revises: 4e69355b1a01
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "835f239aa101"
down_revision: str | None = "4e69355b1a01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"independent_evaluation",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
		sa.Column("storage_key", sa.Text(), nullable=False),
		sa.Column("original_name", sa.Text(), nullable=False),
		sa.Column("media_type", sa.Text(), nullable=False),
		sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
		sa.Column("score", sa.Integer()),
		sa.Column("suggestions", JSONB()),
		sa.Column("improved_resume_key", sa.Text()),
		sa.Column("improved_resume_unlocked_at", sa.DateTime(timezone=True)),
		sa.Column("normalized_facts", JSONB()),
		sa.Column("safe_error", sa.Text()),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
		sa.Column("completed_at", sa.DateTime(timezone=True)),
		sa.CheckConstraint("status IN ('queued', 'processing', 'complete', 'failed')", name="ck_independent_evaluation_status"),
	)
	op.create_table(
		"point_ledger_entry",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
		sa.Column("amount", sa.Integer(), nullable=False),
		sa.Column("reason", sa.Text(), nullable=False),
		sa.Column("idempotency_key", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
		sa.CheckConstraint("amount <> 0", name="ck_point_ledger_entry_nonzero_amount"),
		sa.UniqueConstraint("user_id", "idempotency_key", name="uq_point_ledger_entry_idempotency"),
	)


def downgrade() -> None:
	op.drop_table("point_ledger_entry")
	op.drop_table("independent_evaluation")
