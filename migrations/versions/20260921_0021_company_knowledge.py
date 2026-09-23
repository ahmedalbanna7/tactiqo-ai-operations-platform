"""Separate personal and organization knowledge without broadening old rows."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0021"
down_revision: str | None = "20260921_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Existing documents and ACL snapshots remain personal."""
    op.add_column(
        "knowledge_documents",
        sa.Column("owner_scope", sa.String(24), nullable=False, server_default="personal"),
    )
    op.create_index("ix_knowledge_documents_owner_scope", "knowledge_documents", ["owner_scope"])
    op.add_column(
        "knowledge_acl_snapshots",
        sa.Column("organization_access", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Remove ownership distinction; use only in controlled rollback."""
    op.drop_column("knowledge_acl_snapshots", "organization_access")
    op.drop_index("ix_knowledge_documents_owner_scope", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "owner_scope")
