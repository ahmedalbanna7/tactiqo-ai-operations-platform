"""Add tenant-scoped encrypted integration connections."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260911_0002"
down_revision: str | Sequence[str] | None = "20260722_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the SaaS integration connection source-of-truth table."""
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("endpoint_url", sa.String(512), nullable=False),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("encrypted_authorization", sa.String(8192), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("owner_actor_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            name="uq_integration_connection_org_name",
        ),
    )
    for column in ("organization_id", "owner_actor_id", "provider", "status"):
        op.create_index(f"ix_integration_connections_{column}", "integration_connections", [column])


def downgrade() -> None:
    """Remove SaaS integration connections."""
    op.drop_table("integration_connections")
