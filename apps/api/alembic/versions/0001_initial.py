"""Create user and account tables."""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

USER_COLUMNS = {
    "id": (False, "text"),
    "name": (False, "text"),
    "email": (False, "text"),
    "email_verified": (False, "boolean"),
    "image": (True, "text"),
    "created_at": (False, "datetime"),
    "updated_at": (False, "datetime"),
}
ACCOUNT_COLUMNS = {
    "id": (False, "text"),
    "account_id": (False, "text"),
    "provider_id": (False, "text"),
    "user_id": (False, "text"),
    "password": (True, "text"),
    "created_at": (False, "datetime"),
    "updated_at": (False, "datetime"),
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
    raise RuntimeError("The initial migration cannot be downgraded safely")


def require_table(
    inspector: sa.Inspector,
    table: str,
    expected_columns: dict[str, tuple[bool, str]],
    primary_key: set[str],
    unique_constraints: set[frozenset[str]],
) -> None:
    columns = {column["name"]: column for column in inspector.get_columns(table)}
    missing = sorted(expected_columns.keys() - columns.keys())
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Existing {table} table is missing columns: {names}")
    incompatible = sorted(
        name
        for name, (nullable, kind) in expected_columns.items()
        if columns[name]["nullable"] != nullable or column_kind(columns[name]["type"]) != kind
    )
    if incompatible:
        names = ", ".join(incompatible)
        raise RuntimeError(f"Existing {table} table has incompatible columns: {names}")

    extra_required = sorted(
        name
        for name, column in columns.items()
        if name not in expected_columns and not column["nullable"] and column["default"] is None
    )
    if extra_required:
        names = ", ".join(extra_required)
        raise RuntimeError(f"Existing {table} table has unsupported required columns: {names}")

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


def column_kind(column_type: object) -> str:
    if isinstance(column_type, sa.Text):
        return "text"
    if isinstance(column_type, sa.Boolean):
        return "boolean"
    if isinstance(column_type, sa.DateTime) and column_type.timezone:
        return "datetime"
    return "unsupported"
