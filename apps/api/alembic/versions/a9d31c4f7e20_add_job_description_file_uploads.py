"""add job description file uploads

Revision ID: a9d31c4f7e20
Revises: 5c8d2f7a1b04
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9d31c4f7e20"
down_revision: str | None = "5c8d2f7a1b04"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("job_version", "source_text", existing_type=sa.Text(), nullable=True)
    op.add_column("job_version", sa.Column("source_storage_key", sa.Text()))
    op.add_column("independent_evaluation", sa.Column("job_description_key", sa.Text()))
    op.add_column("independent_evaluation", sa.Column("job_description_media_type", sa.Text()))


def downgrade() -> None:
    op.drop_column("independent_evaluation", "job_description_media_type")
    op.drop_column("independent_evaluation", "job_description_key")
    op.drop_column("job_version", "source_storage_key")
    op.execute("DELETE FROM job_version WHERE source_text IS NULL")
    op.alter_column("job_version", "source_text", existing_type=sa.Text(), nullable=False)
