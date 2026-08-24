"""constrain extraction quality states

Revision ID: c4f2e8a91370
Revises: a9d31c4f7e20
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4f2e8a91370"
down_revision: str | None = "a9d31c4f7e20"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.create_check_constraint(
		"ck_resume_version_quality_state",
		"resume_version",
		"quality_state IN ('pending', 'ready', 'review_required', 'failed')",
	)
	op.create_check_constraint(
		"ck_evaluation_quality_state",
		"evaluation",
		"quality_state IN ('pending', 'ready', 'review_required', 'failed')",
	)


def downgrade() -> None:
	op.drop_constraint("ck_evaluation_quality_state", "evaluation", type_="check")
	op.drop_constraint("ck_resume_version_quality_state", "resume_version", type_="check")
