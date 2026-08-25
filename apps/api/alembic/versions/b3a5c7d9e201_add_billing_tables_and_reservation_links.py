"""add billing tables and reservation links

Revision ID: b3a5c7d9e201
Revises: c5e9f7a2d810
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "b3a5c7d9e201"
down_revision: str | None = "c5e9f7a2d810"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"organization_entitlement",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column(
			"organization_id",
			sa.Text(),
			sa.ForeignKey("organization.id", ondelete="CASCADE"),
			nullable=False,
			unique=True,
		),
		sa.Column("provisioned_by", sa.Text()),
		sa.Column("note", sa.Text()),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
	)
	op.create_table(
		"weekly_free_use",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column(
			"user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
		),
		sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("user_id", "week_start", name="uq_weekly_free_use"),
	)
	op.create_table(
		"razorpay_order",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("razorpay_order_id", sa.Text(), nullable=False, unique=True),
		sa.Column(
			"account_id",
			sa.Text(),
			sa.ForeignKey("point_account.id", ondelete="RESTRICT"),
			nullable=False,
		),
		sa.Column(
			"purchaser_user_id",
			sa.Text(),
			sa.ForeignKey("user.id", ondelete="RESTRICT"),
			nullable=False,
		),
		sa.Column("pack_id", sa.Text(), nullable=False),
		sa.Column("points", sa.Integer(), nullable=False),
		sa.Column("amount_inr", sa.Integer(), nullable=False),
		sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'INR'")),
		sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'created'")),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint(
			"status IN ('created', 'paid', 'refunded', 'failed')",
			name="ck_razorpay_order_status",
		),
	)
	op.create_table(
		"razorpay_payment",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("razorpay_payment_id", sa.Text(), nullable=False, unique=True),
		sa.Column(
			"order_row_id",
			sa.Text(),
			sa.ForeignKey("razorpay_order.id", ondelete="RESTRICT"),
			nullable=False,
		),
		sa.Column("status", sa.Text(), nullable=False),
		sa.Column("method", sa.Text()),
		sa.Column("amount_inr", sa.Integer(), nullable=False),
		sa.Column("refunded_inr", sa.Integer(), nullable=False, server_default=sa.text("0")),
		sa.Column("points_granted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
		sa.Column("signature_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
		sa.Column("source", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
	)
	op.create_table(
		"razorpay_webhook_event",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("event_type", sa.Text(), nullable=False),
		sa.Column("payload", JSONB(), nullable=False),
		sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("processed_at", sa.DateTime(timezone=True)),
	)
	op.add_column(
		"independent_evaluation",
		sa.Column(
			"point_reservation_id",
			sa.Text(),
			sa.ForeignKey("point_reservation.id", ondelete="SET NULL"),
		),
	)
	op.add_column(
		"independent_evaluation",
		sa.Column("free_week_start", sa.DateTime(timezone=True)),
	)
	op.add_column(
		"evaluation",
		sa.Column(
			"point_reservation_id",
			sa.Text(),
			sa.ForeignKey("point_reservation.id", ondelete="SET NULL"),
		),
	)


def downgrade() -> None:
	op.drop_column("evaluation", "point_reservation_id")
	op.drop_column("independent_evaluation", "free_week_start")
	op.drop_column("independent_evaluation", "point_reservation_id")
	op.drop_table("razorpay_webhook_event")
	op.drop_table("razorpay_payment")
	op.drop_table("razorpay_order")
	op.drop_table("weekly_free_use")
	op.drop_table("organization_entitlement")
