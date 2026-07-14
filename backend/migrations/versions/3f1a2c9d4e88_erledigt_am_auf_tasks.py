"""erledigt_am auf Tasks

Revision ID: 3f1a2c9d4e88
Revises: 24717798b82d
Create Date: 2026-07-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3f1a2c9d4e88"
down_revision: Union[str, Sequence[str], None] = "24717798b82d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("erledigt_am", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "erledigt_am")
