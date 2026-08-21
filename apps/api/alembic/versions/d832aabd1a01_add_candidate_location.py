"""add candidate location

Revision ID: d832aabd1a01
Revises: 835f239aa101
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d832aabd1a01"
down_revision: str | None = "835f239aa101"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.add_column("candidate_record", sa.Column("location", sa.Text()))


def downgrade() -> None:
	op.drop_column("candidate_record", "location")
