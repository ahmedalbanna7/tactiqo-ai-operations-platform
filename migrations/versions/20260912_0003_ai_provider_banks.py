"""Add tenant AI provider profiles and sanitized accounting.

Revision ID: 20260912_0003
Revises: 7b285f2ac567
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260912_0003"
down_revision: str | Sequence[str] | None = "7b285f2ac567"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create F3 truth tables."""
    op.create_table(
        "ai_provider_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=96), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("secret_reference", sa.String(length=256), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("maximum_retries", sa.Integer(), nullable=False),
        sa.Column("maximum_concurrency", sa.Integer(), nullable=False),
        sa.Column("daily_unit_limit", sa.BigInteger(), nullable=False),
        sa.Column("classifications_json", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name"),
    )
    op.create_index(
        "ix_ai_provider_profiles_organization_id", "ai_provider_profiles", ["organization_id"]
    )
    op.create_table(
        "ai_provider_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("profile_name", sa.String(length=96), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=96), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_provider_usage_organization_id", "ai_provider_usage", ["organization_id"]
    )
    op.create_index("ix_ai_provider_usage_created_at", "ai_provider_usage", ["created_at"])


def downgrade() -> None:
    """Remove F3 truth tables."""
    op.drop_index("ix_ai_provider_usage_created_at", table_name="ai_provider_usage")
    op.drop_index("ix_ai_provider_usage_organization_id", table_name="ai_provider_usage")
    op.drop_table("ai_provider_usage")
    op.drop_index("ix_ai_provider_profiles_organization_id", table_name="ai_provider_profiles")
    op.drop_table("ai_provider_profiles")
