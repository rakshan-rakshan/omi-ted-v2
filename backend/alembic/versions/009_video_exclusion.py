"""Add soft-remove ("recycle bin") columns to videos

Revision ID: 009
Revises: 008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("excluded_scope", sa.String(length=20), nullable=True))
    op.add_column("videos", sa.Column("excluded_reason", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("excluded_at", sa.DateTime(), nullable=True))
    op.create_index("ix_videos_excluded_scope", "videos", ["excluded_scope"])


def downgrade() -> None:
    op.drop_index("ix_videos_excluded_scope", table_name="videos")
    # SQLite cannot DROP COLUMN without table rebuild — use batch mode.
    with op.batch_alter_table("videos") as batch_op:
        batch_op.drop_column("excluded_at")
        batch_op.drop_column("excluded_reason")
        batch_op.drop_column("excluded_scope")
