"""merge independent evaluation heads

Revision ID: f1c9b92d5e04
Revises: d832aabd1a01, e1f8a04e4132
Create Date: 2026-08-21
"""

from collections.abc import Sequence

revision: str = "f1c9b92d5e04"
down_revision: tuple[str, str] = ("d832aabd1a01", "e1f8a04e4132")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	pass


def downgrade() -> None:
	pass
