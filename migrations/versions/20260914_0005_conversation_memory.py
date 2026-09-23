"""Add tenant-scoped rolling conversation memory.

Revision ID: 20260914_0005
Revises: 20260913_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0005"
down_revision: str | Sequence[str] | None = "20260913_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the isolated rolling-summary table."""
    op.create_table(
        "chat_conversation_memories",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("summarized_message_count", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_chat_conversation_memories_organization_id",
        "chat_conversation_memories",
        ["organization_id"],
    )
    op.create_index(
        "ix_chat_conversation_memories_actor_id",
        "chat_conversation_memories",
        ["actor_id"],
    )


def downgrade() -> None:
    """Remove rolling conversation memory."""
    op.drop_index("ix_chat_conversation_memories_actor_id", table_name="chat_conversation_memories")
    op.drop_index(
        "ix_chat_conversation_memories_organization_id",
        table_name="chat_conversation_memories",
    )
    op.drop_table("chat_conversation_memories")
