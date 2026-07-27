"""Bereiche: arbeit und privat als getrennte Welten

Revision ID: a9ee59769253
Revises: b2781c2ff907
Create Date: 2026-07-27 20:17:53.645801

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9ee59769253'
down_revision: Union[str, Sequence[str], None] = 'b2781c2ff907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BEREICH = sa.Column('bereich', sa.String(length=10), server_default='arbeit', nullable=False)


def upgrade() -> None:
    """Bestandsdaten laufen über den server_default in den Bereich arbeit."""
    op.add_column('tasks', BEREICH.copy())
    op.create_index(op.f('ix_tasks_bereich'), 'tasks', ['bereich'], unique=False)
    op.add_column('time_blocks', BEREICH.copy())
    op.create_index(op.f('ix_time_blocks_bereich'), 'time_blocks', ['bereich'], unique=False)
    # Batch-Modus wegen SQLite (kein ALTER ADD CONSTRAINT); auf Postgres normale ALTERs.
    with op.batch_alter_table('work_schedules') as batch:
        batch.add_column(BEREICH.copy())
        batch.create_unique_constraint('uq_work_schedules_bereich', ['bereich'])


def downgrade() -> None:
    with op.batch_alter_table('work_schedules') as batch:
        batch.drop_constraint('uq_work_schedules_bereich', type_='unique')
        batch.drop_column('bereich')
    op.drop_index(op.f('ix_time_blocks_bereich'), table_name='time_blocks')
    op.drop_column('time_blocks', 'bereich')
    op.drop_index(op.f('ix_tasks_bereich'), table_name='tasks')
    op.drop_column('tasks', 'bereich')
