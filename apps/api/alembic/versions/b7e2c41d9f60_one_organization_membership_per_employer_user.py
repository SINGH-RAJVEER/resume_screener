"""one organization membership per employer user

Revision ID: b7e2c41d9f60
Revises: 9d4c81f6a2b3
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import and_, exists, or_, select

from alembic import op

revision: str = "b7e2c41d9f60"
down_revision: str | None = "9d4c81f6a2b3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    # Keep each user's earliest membership (created_at, id) and drop the rest
    # so the new unique constraint cannot fail on existing data.
    metadata = sa.MetaData()
    member = sa.Table("organization_member", metadata, autoload_with=connection)
    earlier = member.alias()
    has_earlier = exists(
        select(1)
        .select_from(earlier)
        .where(
            earlier.c.user_id == member.c.user_id,
            or_(
                earlier.c.created_at < member.c.created_at,
                and_(
                    earlier.c.created_at == member.c.created_at,
                    earlier.c.id < member.c.id,
                ),
            ),
        )
    )
    connection.execute(member.delete().where(has_earlier))
    op.create_unique_constraint("uq_organization_member_user", "organization_member", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_organization_member_user", "organization_member", type_="unique")
