"""Add tenant-owned MCP action mappings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0017"
down_revision: str | None = "20260916_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create exact action-to-tool mappings per tenant."""
    op.create_table(
        "artifact_action_provider_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("destination_type", sa.String(48), nullable=False),
        sa.Column("tool_name", sa.String(256), nullable=False),
        sa.Column("destination_field", sa.String(96), nullable=False),
        sa.Column("content_field", sa.String(96), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "action", "destination_type", name="uq_action_mapping_scope"
        ),
    )
    op.create_index(
        "ix_action_mapping_org", "artifact_action_provider_mappings", ["organization_id"]
    )


def downgrade() -> None:
    """Remove MCP action mappings."""
    op.drop_table("artifact_action_provider_mappings")
