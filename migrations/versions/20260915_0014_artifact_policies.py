"""Add tenant artifact brand, retention, and quota policy."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0014"
down_revision: str | None = "20260915_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create one authoritative artifact policy per organization."""
    op.create_table(
        "organization_artifact_policies",
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("brand_name", sa.String(120), nullable=False),
        sa.Column("footer_text", sa.String(500), nullable=False),
        sa.Column("require_classification_mark", sa.Boolean(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("monthly_artifact_limit", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organization_id"),
        sa.CheckConstraint("retention_days BETWEEN 1 AND 3650", name="ck_artifact_retention"),
        sa.CheckConstraint(
            "monthly_artifact_limit BETWEEN 1 AND 100000", name="ck_artifact_monthly_limit"
        ),
    )


def downgrade() -> None:
    """Remove tenant artifact policies."""
    op.drop_table("organization_artifact_policies")
