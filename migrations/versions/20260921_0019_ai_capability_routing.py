"""Allow multiple AI providers with capability-aware routing."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0019"
down_revision: str | None = "20260916_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add safe routing metadata; existing profiles remain general-purpose."""
    op.add_column(
        "ai_provider_profiles",
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default='["general"]'),
    )
    op.add_column(
        "ai_provider_profiles",
        sa.Column("routing_priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.create_index(
        "ix_ai_provider_profiles_routing",
        "ai_provider_profiles",
        ["organization_id", "kind", "status", "routing_priority"],
    )


def downgrade() -> None:
    """Remove capability routing metadata."""
    op.drop_index("ix_ai_provider_profiles_routing", table_name="ai_provider_profiles")
    op.drop_column("ai_provider_profiles", "routing_priority")
    op.drop_column("ai_provider_profiles", "capabilities_json")
