"""add demo account flag

Revision ID: f6a3b8c2d1e9
Revises: e7c2d4a8b9f1
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a3b8c2d1e9"
down_revision: str | None = "e7c2d4a8b9f1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("user", "is_demo")
