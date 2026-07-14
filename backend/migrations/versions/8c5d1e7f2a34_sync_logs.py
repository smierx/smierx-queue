"""sync_logs

Revision ID: 8c5d1e7f2a34
Revises: 3f1a2c9d4e88
Create Date: 2026-07-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c5d1e7f2a34"
down_revision: Union[str, Sequence[str], None] = "3f1a2c9d4e88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("(CURRENT_TIMESTAMP)")
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "sync_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("zeitpunkt", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("aktion", sa.String(length=30), nullable=False),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sync_logs_user_id"), "sync_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sync_logs_user_id"), table_name="sync_logs")
    op.drop_table("sync_logs")
