"""Add tenant-scoped pgvector embeddings and lexical index."""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0011"
down_revision: str | None = "20260914_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create vector storage and the lexical half of hybrid retrieval."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_embedding_spaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("space_key", sa.String(96), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "space_key", name="uq_knowledge_embedding_space"),
    )
    op.create_index("ix_embedding_space_org", "knowledge_embedding_spaces", ["organization_id"])
    op.execute(
        """CREATE TABLE knowledge_chunk_embeddings (
        chunk_id uuid NOT NULL REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
        embedding_space_id uuid NOT NULL REFERENCES knowledge_embedding_spaces(id) ON DELETE CASCADE,
        embedding vector NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (chunk_id, embedding_space_id))"""
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_lexical ON knowledge_chunks "
        "USING gin (to_tsvector('simple', normalized_text))"
    )


def downgrade() -> None:
    """Remove derived retrieval storage while preserving canonical content."""
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_lexical")
    op.execute("DROP TABLE IF EXISTS knowledge_chunk_embeddings")
    op.drop_index("ix_embedding_space_org", table_name="knowledge_embedding_spaces")
    op.drop_table("knowledge_embedding_spaces")
