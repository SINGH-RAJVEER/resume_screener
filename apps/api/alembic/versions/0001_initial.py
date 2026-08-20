"""Create user and account tables."""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

USER_COLUMNS = {
    "id": False,
    "name": False,
    "email": False,
    "email_verified": False,
    "image": True,
    "created_at": False,
    "updated_at": False,
}
ACCOUNT_COLUMNS = {
    "id": False,
    "account_id": False,
    "provider_id": False,
    "user_id": False,
    "password": True,
    "created_at": False,
    "updated_at": False,
}


def upgrade() -> None:
    connection = op.get_bind()
    inspector = inspect(connection)

    if inspector.has_table("user"):
        require_table(inspector, "user", USER_COLUMNS, {"id"}, {frozenset({"email"})})
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
        require_table(
            inspector,
            "account",
            ACCOUNT_COLUMNS,
            {"id"},
            {frozenset({"provider_id", "account_id"})},
        )
        require_account_user_foreign_key(inspector)
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


def require_table(
    inspector: sa.Inspector,
    table: str,
    expected_columns: dict[str, bool],
    primary_key: set[str],
    unique_constraints: set[frozenset[str]],
) -> None:
    columns = {column["name"]: column["nullable"] for column in inspector.get_columns(table)}
    missing = sorted(expected_columns.keys() - columns.keys())
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Existing {table} table is missing columns: {names}")
    wrong_nullability = sorted(
        name for name, nullable in expected_columns.items() if columns[name] != nullable
    )
    if wrong_nullability:
        names = ", ".join(wrong_nullability)
        raise RuntimeError(f"Existing {table} table has incompatible columns: {names}")

    existing_primary_key = set(inspector.get_pk_constraint(table)["constrained_columns"])
    if existing_primary_key != primary_key:
        raise RuntimeError(f"Existing {table} table has an incompatible primary key")

    existing_unique_constraints = {
        frozenset(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table)
    }
    if not unique_constraints <= existing_unique_constraints:
        raise RuntimeError(f"Existing {table} table is missing a unique constraint")


def require_account_user_foreign_key(inspector: sa.Inspector) -> None:
    for foreign_key in inspector.get_foreign_keys("account"):
        if (
            foreign_key["constrained_columns"] == ["user_id"]
            and foreign_key["referred_table"] == "user"
            and foreign_key["referred_columns"] == ["id"]
            and foreign_key["options"].get("ondelete") == "CASCADE"
        ):
            return
    raise RuntimeError("Existing account table has an incompatible user foreign key")


def has_constraint(inspector: sa.Inspector, table: str, name: str) -> bool:
    if not inspector.has_table(table):
        return False
    return any(constraint["name"] == name for constraint in inspector.get_unique_constraints(table))
