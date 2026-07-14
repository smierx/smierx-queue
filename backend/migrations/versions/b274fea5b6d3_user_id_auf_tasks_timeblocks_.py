"""user_id auf Tasks, TimeBlocks, WorkSchedules

Revision ID: b274fea5b6d3
Revises: 66d4b8d455d4
Create Date: 2026-07-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b274fea5b6d3"
down_revision: Union[str, Sequence[str], None] = "66d4b8d455d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _user_spalte() -> sa.Column:
    # Bestandszeilen aus der Zeit vor Keycloak gehören dem Dev-User.
    return sa.Column("user_id", sa.String(length=100), nullable=False, server_default="dev")


def upgrade() -> None:
    op.add_column("tasks", _user_spalte())
    op.create_index(op.f("ix_tasks_user_id"), "tasks", ["user_id"], unique=False)
    op.add_column("time_blocks", _user_spalte())
    op.create_index(op.f("ix_time_blocks_user_id"), "time_blocks", ["user_id"], unique=False)
    with op.batch_alter_table("work_schedules") as batch:
        batch.add_column(_user_spalte())
        batch.create_unique_constraint("uq_work_schedules_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("work_schedules") as batch:
        batch.drop_constraint("uq_work_schedules_user_id", type_="unique")
        batch.drop_column("user_id")
    op.drop_index(op.f("ix_time_blocks_user_id"), table_name="time_blocks")
    op.drop_column("time_blocks", "user_id")
    op.drop_index(op.f("ix_tasks_user_id"), table_name="tasks")
    op.drop_column("tasks", "user_id")
