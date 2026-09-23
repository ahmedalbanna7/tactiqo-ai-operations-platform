"""Add bounded retry and compensation state to artifact actions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0016"
down_revision: str | None = "20260915_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add retry bounds and a provider-safe compensation reference."""
    op.add_column(
        "artifact_action_runs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "artifact_action_runs",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "artifact_action_runs", sa.Column("compensation_reference", sa.String(255))
    )
    op.create_check_constraint(
        "ck_artifact_action_attempts",
        "artifact_action_runs",
        "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10",
    )


def downgrade() -> None:
    """Remove bounded retry and compensation fields."""
    op.drop_constraint(
        "ck_artifact_action_attempts", "artifact_action_runs", type_="check"
    )
    op.drop_column("artifact_action_runs", "compensation_reference")
    op.drop_column("artifact_action_runs", "max_attempts")
    op.drop_column("artifact_action_runs", "attempt_count")
