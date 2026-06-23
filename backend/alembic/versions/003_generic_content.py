"""Make messages.video_id nullable, add source_type, source_url, author

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"

    op.add_column("messages", sa.Column("source_type", sa.String(20), server_default="youtube", nullable=False))
    op.add_column("messages", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("author", sa.String(200), nullable=True))
    if is_pg:
        op.alter_column("messages", "video_id", nullable=True)
    op.create_index("ix_messages_source_type", "messages", ["source_type"])


def downgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"

    op.drop_index("ix_messages_source_type", table_name="messages")
    if is_pg:
        op.alter_column("messages", "video_id", nullable=False)
    op.drop_column("messages", "author")
    op.drop_column("messages", "source_url")
    op.drop_column("messages", "source_type")
