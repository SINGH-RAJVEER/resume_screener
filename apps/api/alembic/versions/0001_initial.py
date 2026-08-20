"""Create user and account tables."""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

USER_COLUMNS = {
    "id",
    "name",
    "email",
    "email_verified",
    "image",
    "created_at",
    "updated_at",
}
ACCOUNT_COLUMNS = {
    "id",
    "account_id",
    "provider_id",
    "user_id",
    "password",
    "created_at",
    "updated_at",
}


def upgrade() -> None:
    connection = op.get_bind()
    inspector = inspect(connection)

    if inspector.has_table("user"):
        require_columns(inspector, "user", USER_COLUMNS)
    else:
        op.create_table(
            "user",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("image", sa.Text()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("email", name="uq_user_email"),
        )

    inspector = inspect(connection)
    if inspector.has_table("account"):
        require_columns(inspector, "account", ACCOUNT_COLUMNS)
    else:
        op.create_table(
            "account",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("account_id", sa.Text(), nullable=False),
            sa.Column("provider_id", sa.Text(), nullable=False),
            sa.Column(
                "user_id",
                sa.Text(),
                sa.ForeignKey("user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("password", sa.Text()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "provider_id",
                "account_id",
                name="uq_account_provider_account",
            ),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if has_constraint(inspector, "account", "uq_account_provider_account"):
        op.drop_table("account")
    if has_constraint(inspector, "user", "uq_user_email"):
        op.drop_table("user")


def require_columns(inspector: sa.Inspector, table: str, required: set[str]) -> None:
    columns = {column["name"] for column in inspector.get_columns(table)}
    missing = sorted(required - columns)
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Existing {table} table is missing columns: {names}")


def has_constraint(inspector: sa.Inspector, table: str, name: str) -> bool:
    if not inspector.has_table(table):
        return False
    return any(constraint["name"] == name for constraint in inspector.get_unique_constraints(table))
