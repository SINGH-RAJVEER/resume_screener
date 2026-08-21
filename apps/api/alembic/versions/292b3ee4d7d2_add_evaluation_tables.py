"""add evaluation tables

Revision ID: 292b3ee4d7d2
Revises: 909ffb252282
Create Date: 2026-08-21 05:45:34.841237
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "292b3ee4d7d2"
down_revision: str | None = "909ffb252282"
branch_labels: Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"evaluation",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("resume_submission_id", sa.Text(), sa.ForeignKey("resume_submission.id", ondelete="CASCADE"), nullable=False),
		sa.Column("job_version_id", sa.Text(), sa.ForeignKey("job_version.id", ondelete="RESTRICT"), nullable=False),
		sa.Column("resume_version_id", sa.Text(), sa.ForeignKey("resume_version.id", ondelete="RESTRICT"), nullable=False),
		sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
		sa.Column("score", sa.Integer()),
		sa.Column("evidence_coverage", sa.Integer()),
		sa.Column("eligibility", sa.Text(), nullable=False, server_default="pending"),
		sa.Column("quality_state", sa.Text(), nullable=False, server_default="pending"),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("completed_at", sa.DateTime(timezone=True)),
		sa.CheckConstraint("eligibility IN ('pending', 'eligible', 'needs_review', 'not_eligible')", name="ck_evaluation_eligibility"),
		sa.UniqueConstraint("resume_submission_id", "job_version_id", name="uq_evaluation_submission_job_version"),
	)
	op.create_table(
		"requirement_assessment",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("evaluation_id", sa.Text(), sa.ForeignKey("evaluation.id", ondelete="CASCADE"), nullable=False),
		sa.Column("job_requirement_id", sa.Text(), sa.ForeignKey("job_requirement.id", ondelete="RESTRICT"), nullable=False),
		sa.Column("outcome", sa.Text(), nullable=False),
		sa.Column("confidence", sa.Float(), nullable=False),
		sa.Column("reasoning", sa.Text(), nullable=False),
		sa.Column("evidence", postgresql.JSONB(), nullable=False),
		sa.Column("deterministic_evidence", postgresql.JSONB()),
		sa.Column("semantic_evidence", postgresql.JSONB()),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint("outcome IN ('met', 'partial', 'not_met', 'unknown')", name="ck_assessment_outcome"),
		sa.UniqueConstraint("evaluation_id", "job_requirement_id", name="uq_assessment_evaluation_requirement"),
	)


def downgrade() -> None:
	op.drop_table("requirement_assessment")
	op.drop_table("evaluation")
