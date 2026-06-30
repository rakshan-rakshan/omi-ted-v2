"""Add chunks.start_time (earliest segment start, for jump-to-moment citations)

Revision ID: 005
Revises: 004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("start_time", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "start_time")
