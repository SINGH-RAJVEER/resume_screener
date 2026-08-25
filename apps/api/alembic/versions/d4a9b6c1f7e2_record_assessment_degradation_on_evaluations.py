"""record assessment degradation on evaluations

Revision ID: d4a9b6c1f7e2
Revises: b3a5c7d9e201
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4a9b6c1f7e2"
down_revision: str | None = "b3a5c7d9e201"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.add_column(
		"evaluation",
		sa.Column("assessment_degradation", sa.Text(), nullable=True),
	)


def downgrade() -> None:
	op.drop_column("evaluation", "assessment_degradation")
