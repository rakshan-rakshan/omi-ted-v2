"""Add translation_costs table for cost and token tracking per video run

Revision ID: 007
Revises: 006
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "translation_costs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "video_id", sa.Integer(),
            sa.ForeignKey("videos.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("run_id", sa.String(length=50), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("segments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_translation_costs_video_id", "translation_costs", ["video_id"])
    op.create_index("ix_translation_costs_run_id", "translation_costs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_translation_costs_run_id", table_name="translation_costs")
    op.drop_index("ix_translation_costs_video_id", table_name="translation_costs")
    op.drop_table("translation_costs")
