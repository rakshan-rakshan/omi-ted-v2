"""Add notebooks + notebook_messages (collections for scoped Q&A)

Revision ID: 006
Revises: 005
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notebooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "notebook_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "notebook_id", sa.Integer(),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "message_id", sa.Integer(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False,
        ),
    )
    op.create_index("ix_notebook_messages_notebook_id", "notebook_messages", ["notebook_id"])
    op.create_index("ix_notebook_messages_message_id", "notebook_messages", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_notebook_messages_message_id", table_name="notebook_messages")
    op.drop_index("ix_notebook_messages_notebook_id", table_name="notebook_messages")
    op.drop_table("notebook_messages")
    op.drop_table("notebooks")
