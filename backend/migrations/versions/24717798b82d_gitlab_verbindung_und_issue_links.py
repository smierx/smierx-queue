"""GitLab-Verbindung und Issue-Links

Revision ID: 24717798b82d
Revises: b274fea5b6d3
Create Date: 2026-07-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "24717798b82d"
down_revision: Union[str, Sequence[str], None] = "b274fea5b6d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("(CURRENT_TIMESTAMP)")
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "gitlab_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=300), nullable=False),
        sa.Column("token", sa.String(length=300), nullable=False),
        sa.Column("projekt_ids", JSON_TYPE, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "gitlab_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("projekt_id", sa.Integer(), nullable=False),
        sa.Column("issue_iid", sa.Integer(), nullable=False),
        sa.Column(
            "zuletzt_gesynct", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
        sa.UniqueConstraint("user_id", "projekt_id", "issue_iid", name="uq_gitlab_links_issue"),
    )
    op.create_index(op.f("ix_gitlab_links_user_id"), "gitlab_links", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gitlab_links_user_id"), table_name="gitlab_links")
    op.drop_table("gitlab_links")
    op.drop_table("gitlab_connections")
