"""Add governed templates, retention, metering, and action ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0015"
down_revision: str | None = "20260915_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend artifacts without deleting historical lineage."""
    op.add_column("artifacts", sa.Column("retention_until", sa.DateTime(timezone=True)))
    op.add_column(
        "artifacts",
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("artifacts", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.create_index("ix_artifacts_retention_until", "artifacts", ["retention_until"])

    op.create_table(
        "artifact_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("artifact_type", sa.String(32), nullable=False),
        sa.Column("output_format", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_artifact_template_org_name"),
    )
    op.create_index("ix_artifact_templates_org", "artifact_templates", ["organization_id"])
    op.create_index("ix_artifact_templates_type", "artifact_templates", ["artifact_type"])

    op.create_table(
        "artifact_usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("stored_bytes", sa.Integer(), nullable=False),
        sa.Column("input_units", sa.Integer(), nullable=False),
        sa.Column("output_units", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("model", sa.String(160)),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("stored_bytes >= 0", name="ck_artifact_usage_bytes"),
        sa.CheckConstraint(
            "input_units >= 0 AND output_units >= 0 AND estimated_cost_micros >= 0",
            name="ck_artifact_usage_nonnegative",
        ),
    )
    op.create_index(
        "ix_artifact_usage_org_created",
        "artifact_usage_records",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "artifact_action_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(128), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("destination_type", sa.String(48), nullable=False),
        sa.Column("destination_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("external_id", sa.String(255)),
        sa.Column("error_code", sa.String(96)),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_artifact_action_key"),
    )
    op.create_index(
        "ix_artifact_actions_org_status",
        "artifact_action_runs",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    """Remove F8 governed execution additions."""
    op.drop_table("artifact_action_runs")
    op.drop_table("artifact_usage_records")
    op.drop_table("artifact_templates")
    op.drop_index("ix_artifacts_retention_until", table_name="artifacts")
    op.drop_column("artifacts", "purged_at")
    op.drop_column("artifacts", "legal_hold")
    op.drop_column("artifacts", "retention_until")
