"""add independent evaluation job text

Revision ID: e1f8a04e4132
Revises: 835f239aa101
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f8a04e4132"
down_revision: str | None = "835f239aa101"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:

	op.add_column("independent_evaluation", sa.Column("job_description", sa.Text()))


def downgrade() -> None:

	op.drop_column("independent_evaluation", "job_description")
