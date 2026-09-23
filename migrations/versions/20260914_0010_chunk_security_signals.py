"""Add document injection signals to retrieval chunks.

Revision ID: 20260914_0010
Revises: 20260914_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0010"
down_revision: str | Sequence[str] | None = "20260914_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist content-security labels without deleting source evidence."""
    op.add_column(
        "knowledge_chunks",
        sa.Column("security_signals", sa.JSON(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    """Remove derived chunk security labels."""
    op.drop_column("knowledge_chunks", "security_signals")
