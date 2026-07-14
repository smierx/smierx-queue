"""Task-Modell, Tags, Termine/Blocker, Arbeitszeit

Revision ID: 66d4b8d455d4
Revises:
Create Date: 2026-07-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "66d4b8d455d4"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("(CURRENT_TIMESTAMP)")
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titel", sa.String(length=300), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("geaendert_am", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_position"), "tasks", ["position"], unique=False)
    op.create_table(
        "time_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titel", sa.String(length=300), nullable=False),
        sa.Column("typ", sa.String(length=20), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ende", sa.DateTime(timezone=True), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_time_blocks_start"), "time_blocks", ["start"], unique=False)
    op.create_table(
        "work_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("modus", sa.String(length=20), nullable=False),
        sa.Column("stunden_pro_tag", sa.Float(), nullable=False),
        sa.Column("zeiten", JSON_TYPE, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tag_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=50), nullable=False),
        sa.Column("aktion", sa.String(length=10), nullable=False),
        sa.Column("zeitpunkt", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tag_events_task_id"), "tag_events", ["task_id"], unique=False)
    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "tag"),
    )


def downgrade() -> None:
    op.drop_table("task_tags")
    op.drop_index(op.f("ix_tag_events_task_id"), table_name="tag_events")
    op.drop_table("tag_events")
    op.drop_table("work_schedules")
    op.drop_index(op.f("ix_time_blocks_start"), table_name="time_blocks")
    op.drop_table("time_blocks")
    op.drop_index(op.f("ix_tasks_position"), table_name="tasks")
    op.drop_table("tasks")
