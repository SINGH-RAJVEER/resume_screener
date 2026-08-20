"""Create the final user and credential account schema."""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS keeps databases created by the Go service usable while Alembic is introduced.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS "user" (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            email_verified BOOLEAN NOT NULL DEFAULT FALSE,
            image TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS account (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            user_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            password TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (provider_id, account_id)
        )
        """
    )


def downgrade() -> None:
    op.drop_table("account")
    op.drop_table("user")
