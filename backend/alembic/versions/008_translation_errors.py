"""Add translation_errors table for per-failure translation error tracking

Revision ID: 008
Revises: 007
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "translation_errors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "video_id", sa.Integer(),
            sa.ForeignKey("videos.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("youtube_id", sa.String(length=20), nullable=True),
        sa.Column("run_id", sa.String(length=50), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("segment_index", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=50), nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_translation_errors_video_id", "translation_errors", ["video_id"])
    op.create_index("ix_translation_errors_youtube_id", "translation_errors", ["youtube_id"])
    op.create_index("ix_translation_errors_run_id", "translation_errors", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_translation_errors_run_id", table_name="translation_errors")
    op.drop_index("ix_translation_errors_youtube_id", table_name="translation_errors")
    op.drop_index("ix_translation_errors_video_id", table_name="translation_errors")
    op.drop_table("translation_errors")
