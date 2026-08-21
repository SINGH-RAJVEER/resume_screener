"""add user account types

Revision ID: 223ba4be33bc
Revises: a206c0cb247f
Create Date: 2026-08-21 06:32:01.034568
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "223ba4be33bc"
down_revision: str | None = "a206c0cb247f"
branch_labels: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user", sa.Column("account_type", sa.Text(), nullable=False, server_default="candidate")
    )
    op.create_check_constraint(
        "ck_user_account_type", "user", "account_type IN ('employer', 'candidate')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_account_type", "user", type_="check")
    op.drop_column("user", "account_type")
