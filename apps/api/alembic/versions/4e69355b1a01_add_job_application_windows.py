"""add job application windows

Revision ID: 4e69355b1a01
Revises: 223ba4be33bc
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4e69355b1a01"
down_revision: str | None = "223ba4be33bc"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.add_column("job", sa.Column("application_opens_at", sa.DateTime(timezone=True)))
	op.add_column("job", sa.Column("application_closes_at", sa.DateTime(timezone=True)))
	op.add_column("invitation", sa.Column("passcode_hash", sa.Text()))
	op.create_unique_constraint("uq_invitation_passcode_hash", "invitation", ["passcode_hash"])


def downgrade() -> None:
	op.drop_constraint("uq_invitation_passcode_hash", "invitation", type_="unique")
	op.drop_column("invitation", "passcode_hash")
	op.drop_column("job", "application_closes_at")
	op.drop_column("job", "application_opens_at")
