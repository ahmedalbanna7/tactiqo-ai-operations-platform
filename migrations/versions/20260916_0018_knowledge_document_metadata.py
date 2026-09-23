"""Add business domain and retrieval purpose to knowledge documents."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0018"
down_revision: str | None = "20260916_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add filterable metadata with safe defaults for historical documents."""
    op.add_column(
        "knowledge_documents",
        sa.Column("domain", sa.String(32), nullable=False, server_default="general"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("purpose", sa.String(32), nullable=False, server_default="research"),
    )
    op.create_index("ix_knowledge_documents_domain", "knowledge_documents", ["domain"])
    op.create_index("ix_knowledge_documents_purpose", "knowledge_documents", ["purpose"])
    # The owner explicitly identified this existing implementation report as project knowledge.
    op.execute(
        "UPDATE knowledge_documents SET domain = 'project', purpose = 'authoritative' "
        "WHERE name = 'F7_IMPLEMENTATION.md'"
    )


def downgrade() -> None:
    """Remove knowledge metadata filters."""
    op.drop_index("ix_knowledge_documents_purpose", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_domain", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "purpose")
    op.drop_column("knowledge_documents", "domain")
