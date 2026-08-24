"""add compiled job requirements

Revision ID: c37a9f8e21d4
Revises: b41c7e2d9a55
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c37a9f8e21d4"
down_revision: str | None = "b41c7e2d9a55"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.add_column(
		"job_requirement",
		sa.Column("category", sa.Text(), server_default="other", nullable=False),
	)
	op.add_column(
		"job_requirement",
		sa.Column("source_modality", sa.Text(), server_default="unclear", nullable=False),
	)
	op.add_column(
		"job_requirement",
		sa.Column("assessability", sa.Text(), server_default="unclear", nullable=False),
	)
	op.add_column(
		"job_requirement",
		sa.Column(
			"predicate",
			postgresql.JSONB(astext_type=sa.Text()),
			server_default=sa.text("'{}'::jsonb"),
			nullable=False,
		),
	)
	op.create_check_constraint(
		"ck_requirement_assessability",
		"job_requirement",
		"assessability IN ('resume_evidence', 'candidate_attestation', "
		"'recruiter_review', 'prohibited', 'unclear')",
	)


def downgrade() -> None:
	op.drop_constraint(
		"ck_requirement_assessability",
		"job_requirement",
		type_="check",
	)
	op.drop_column("job_requirement", "predicate")
	op.drop_column("job_requirement", "assessability")
	op.drop_column("job_requirement", "source_modality")
	op.drop_column("job_requirement", "category")
