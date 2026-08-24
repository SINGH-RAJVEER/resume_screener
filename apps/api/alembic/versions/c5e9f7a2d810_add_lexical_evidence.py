"""add lexical evidence to requirement assessments

Revision ID: c5e9f7a2d810
Revises: 7a1c2d9e4b05
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "c5e9f7a2d810"
down_revision: str | None = "7a1c2d9e4b05"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.add_column(
		"requirement_assessment",
		sa.Column("lexical_evidence", JSONB(), nullable=True),
	)


def downgrade() -> None:
	op.drop_column("requirement_assessment", "lexical_evidence")
