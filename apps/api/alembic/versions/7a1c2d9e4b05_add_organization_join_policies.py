"""add organization join policies

Revision ID: 7a1c2d9e4b05
Revises: c37a9f8e21d4
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7a1c2d9e4b05"
down_revision: str | None = "c37a9f8e21d4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.add_column(
		"organization",
		sa.Column(
			"default_member_role", sa.Text(), nullable=False, server_default=sa.text("'viewer'")
		),
	)
	op.create_check_constraint(
		"ck_organization_default_member_role",
		"organization",
		"default_member_role IN ('recruiter', 'viewer')",
	)
	op.create_table(
		"organization_email_domain",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column(
			"organization_id",
			sa.Text(),
			sa.ForeignKey("organization.id", ondelete="CASCADE"),
			nullable=False,
		),
		sa.Column("domain", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("domain", name="uq_organization_email_domain"),
	)
	op.create_table(
		"organization_allowed_email",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column(
			"organization_id",
			sa.Text(),
			sa.ForeignKey("organization.id", ondelete="CASCADE"),
			nullable=False,
		),
		sa.Column("email", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("organization_id", "email", name="uq_organization_allowed_email"),
	)


def downgrade() -> None:
	op.drop_table("organization_allowed_email")
	op.drop_table("organization_email_domain")
	op.drop_constraint("ck_organization_default_member_role", "organization", type_="check")
	op.drop_column("organization", "default_member_role")
