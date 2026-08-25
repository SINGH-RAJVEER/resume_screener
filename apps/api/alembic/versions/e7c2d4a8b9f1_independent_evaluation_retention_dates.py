"""independent evaluation retention dates

Revision ID: e7c2d4a8b9f1
Revises: d4a9b6c1f7e2
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7c2d4a8b9f1"
down_revision: str | None = "d4a9b6c1f7e2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	# Existing rows get the 30-day default window counted from migration time.
	op.add_column(
		"independent_evaluation",
		sa.Column(
			"retention_date",
			sa.DateTime(timezone=True),
			nullable=False,
			server_default=sa.text("now() + interval '30 days'"),
		),
	)


def downgrade() -> None:
	op.drop_column("independent_evaluation", "retention_date")
