"""RAG schema: translation_cache, messages, chunks, query_logs

Revision ID: 002
Revises: 001
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"

    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        from pgvector.sqlalchemy import Vector as PgVector
        embedding_type = PgVector(384)
    else:
        embedding_type = sa.Text()

    op.create_table(
        "translation_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
        sa.Column("te_text", sa.Text(), nullable=False),
        sa.Column("en_text", sa.Text(), nullable=False),
        sa.Column("src_lang", sa.String(10), nullable=False),
        sa.Column("tgt_lang", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_translation_cache_cache_key", "translation_cache", ["cache_key"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("message_type", sa.String(20), nullable=False, server_default="sermon"),
        sa.Column("series", sa.String(200)),
        sa.Column("language", sa.String(5), nullable=False, server_default="te"),
        sa.Column("scripture_refs", sa.Text()),  # JSON array for SQLite compat
        sa.Column("themes", sa.Text()),           # JSON array
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_messages_video_id", "messages", ["video_id"])
    op.create_index("ix_messages_message_type", "messages", ["message_type"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(5), nullable=False, server_default="en"),
        sa.Column("token_count", sa.Integer()),
        sa.Column("embedding", embedding_type),
        sa.Column("scripture_refs", sa.Text()),  # JSON array
        sa.Column("topic_tags", sa.Text()),       # JSON array
    )
    op.create_index("ix_chunks_message_id", "chunks", ["message_id"])

    if is_pg:
        op.create_index(
            "ix_chunks_fts", "chunks",
            [sa.text("to_tsvector('english', chunk_text)")],
            postgresql_using="gin",
        )

    op.create_table(
        "query_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("filters", sa.Text()),               # JSON
        sa.Column("retrieved_chunk_ids", sa.Text()),   # JSON
        sa.Column("answer_text", sa.Text()),
        sa.Column("citations", sa.Text()),             # JSON
        sa.Column("feedback_score", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("model_used", sa.String(50)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_query_logs_created_at", "query_logs", ["created_at"])

    if is_pg:
        try:
            op.execute(
                "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
                "USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 200)"
            )
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"

    if is_pg:
        op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
        op.execute("DROP INDEX IF EXISTS ix_chunks_fts")

    op.drop_index("ix_query_logs_created_at", table_name="query_logs")
    op.drop_table("query_logs")
    op.drop_index("ix_chunks_message_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_messages_video_id", table_name="messages")
    op.drop_index("ix_messages_message_type", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_translation_cache_cache_key", table_name="translation_cache")
    op.drop_table("translation_cache")
