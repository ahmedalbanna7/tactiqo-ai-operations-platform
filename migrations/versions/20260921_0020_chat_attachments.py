"""Persist authorized knowledge attachments shown inside chat."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0020"
down_revision: str | None = "20260921_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create scoped conversation attachment references."""
    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "document_id", name="uq_chat_attachment_document"),
    )
    op.create_index("ix_chat_attachments_conversation_id", "chat_attachments", ["conversation_id"])
    op.create_index("ix_chat_attachments_document_id", "chat_attachments", ["document_id"])
    op.create_index("ix_chat_attachments_organization_id", "chat_attachments", ["organization_id"])
    op.create_index("ix_chat_attachments_actor_id", "chat_attachments", ["actor_id"])


def downgrade() -> None:
    """Remove conversation attachment references."""
    op.drop_table("chat_attachments")
