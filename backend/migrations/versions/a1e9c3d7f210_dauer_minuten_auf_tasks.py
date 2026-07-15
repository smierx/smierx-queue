"""dauer_minuten auf Tasks

Revision ID: a1e9c3d7f210
Revises: 8c5d1e7f2a34
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1e9c3d7f210"
down_revision: Union[str, Sequence[str], None] = "8c5d1e7f2a34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("dauer_minuten", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("tasks", "dauer_minuten")
