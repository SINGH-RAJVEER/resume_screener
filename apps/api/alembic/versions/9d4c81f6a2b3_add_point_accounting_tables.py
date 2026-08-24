"""add point accounting tables

Revision ID: 9d4c81f6a2b3
Revises: 7a1c2d9e4b05
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d4c81f6a2b3"
down_revision: str | None = "7a1c2d9e4b05"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.drop_table("point_ledger_entry")
	op.create_table(
		"point_account",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("owner_user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="CASCADE")),
		sa.Column(
			"organization_id", sa.Text(), sa.ForeignKey("organization.id", ondelete="CASCADE")
		),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint(
			"(owner_user_id IS NOT NULL) <> (organization_id IS NOT NULL)",
			name="ck_point_account_owner",
		),
		sa.UniqueConstraint("owner_user_id", name="uq_point_account_user"),
		sa.UniqueConstraint("organization_id", name="uq_point_account_organization"),
	)
	op.create_table(
		"point_ledger_entry",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column(
			"account_id",
			sa.Text(),
			sa.ForeignKey("point_account.id", ondelete="CASCADE"),
			nullable=False,
		),
		sa.Column("amount", sa.Integer(), nullable=False),
		sa.Column("reason", sa.Text(), nullable=False),
		sa.Column("idempotency_key", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint("amount <> 0", name="ck_point_ledger_entry_nonzero_amount"),
		sa.UniqueConstraint("account_id", "idempotency_key", name="uq_point_ledger_entry_idempotency"),
	)
	op.create_table(
		"point_reservation",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column(
			"account_id",
			sa.Text(),
			sa.ForeignKey("point_account.id", ondelete="CASCADE"),
			nullable=False,
		),
		sa.Column("amount", sa.Integer(), nullable=False),
		sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'reserved'")),
		sa.Column("purpose", sa.Text(), nullable=False),
		sa.Column("idempotency_key", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint("amount > 0", name="ck_point_reservation_positive_amount"),
		sa.CheckConstraint(
			"state IN ('reserved', 'settled', 'released')", name="ck_point_reservation_state"
		),
		sa.UniqueConstraint("account_id", "idempotency_key", name="uq_point_reservation_idempotency"),
	)


def downgrade() -> None:
	op.drop_table("point_reservation")
	op.drop_table("point_ledger_entry")
	op.drop_table("point_account")
	op.create_table(
		"point_ledger_entry",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
		sa.Column("amount", sa.Integer(), nullable=False),
		sa.Column("reason", sa.Text(), nullable=False),
		sa.Column("idempotency_key", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint("amount <> 0", name="ck_point_ledger_entry_nonzero_amount"),
		sa.UniqueConstraint("user_id", "idempotency_key", name="uq_point_ledger_entry_idempotency"),
	)
