"""Add explicit subject and tool grants for SaaS MCP connections.

Revision ID: 20260914_0008
Revises: 20260914_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0008"
down_revision: str | Sequence[str] | None = "20260914_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create fail-closed per-tool grants; existing connections receive no implicit access."""
    op.create_table(
        "connection_tool_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("subject_type", sa.String(24), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("tool_name", sa.String(160), nullable=False),
        sa.Column("permission", sa.String(24), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["integration_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "subject_type",
            "subject_id",
            "tool_name",
            name="uq_connection_subject_tool_grant",
        ),
    )
    op.create_index(
        "ix_connection_tool_grants_connection_id", "connection_tool_grants", ["connection_id"]
    )
    op.create_index(
        "ix_connection_tool_grants_organization_id", "connection_tool_grants", ["organization_id"]
    )
    op.create_index(
        "ix_connection_tool_grants_subject_id", "connection_tool_grants", ["subject_id"]
    )
    op.create_index(
        "ix_connection_tool_grants_subject_type", "connection_tool_grants", ["subject_type"]
    )


def downgrade() -> None:
    """Remove scoped connection grants."""
    op.drop_index("ix_connection_tool_grants_subject_type", table_name="connection_tool_grants")
    op.drop_index("ix_connection_tool_grants_subject_id", table_name="connection_tool_grants")
    op.drop_index("ix_connection_tool_grants_organization_id", table_name="connection_tool_grants")
    op.drop_index("ix_connection_tool_grants_connection_id", table_name="connection_tool_grants")
    op.drop_table("connection_tool_grants")
