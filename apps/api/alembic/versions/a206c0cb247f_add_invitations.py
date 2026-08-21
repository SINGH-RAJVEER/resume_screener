"""add invitations

Revision ID: a206c0cb247f
Revises: 292b3ee4d7d2
Create Date: 2026-08-21 06:10:45.604103
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a206c0cb247f"
down_revision: str | None = "292b3ee4d7d2"
branch_labels: Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"invitation",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("job_id", sa.Text(), sa.ForeignKey("job.id", ondelete="CASCADE"), nullable=False),
		sa.Column("creator_user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
		sa.Column("token_hash", sa.Text(), nullable=False),
		sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("redeeming_user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="SET NULL")),
		sa.Column("resume_submission_id", sa.Text(), sa.ForeignKey("resume_submission.id", ondelete="SET NULL")),
		sa.Column("revoked_at", sa.DateTime(timezone=True)),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("token_hash", name="uq_invitation_token_hash"),
	)


def downgrade() -> None:
	op.drop_table("invitation")
