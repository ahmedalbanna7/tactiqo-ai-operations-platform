"""Add encrypted AI provider credential references.

Revision ID: 20260913_0004
Revises: 20260912_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260913_0004"
down_revision: str | Sequence[str] | None = "20260912_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the encrypted local-development credential store."""
    op.create_table(
        "ai_provider_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("reference", sa.String(length=96), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("last_four", sa.String(length=4), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index(
        "ix_ai_provider_credentials_organization_id",
        "ai_provider_credentials",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_provider_credentials_reference",
        "ai_provider_credentials",
        ["reference"],
        unique=True,
    )


def downgrade() -> None:
    """Remove AI provider credential storage."""
    op.drop_index("ix_ai_provider_credentials_reference", table_name="ai_provider_credentials")
    op.drop_index(
        "ix_ai_provider_credentials_organization_id", table_name="ai_provider_credentials"
    )
    op.drop_table("ai_provider_credentials")
