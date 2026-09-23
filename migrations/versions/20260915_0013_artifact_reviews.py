"""Add independent artifact review decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0013"
down_revision: str | None = "20260915_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable review records for artifact versions."""
    op.create_table(
        "artifact_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("comment", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "version_number", name="uq_artifact_review_version"),
    )
    op.create_index("ix_artifact_reviews_artifact_id", "artifact_reviews", ["artifact_id"])
    op.create_index("ix_artifact_reviews_decision", "artifact_reviews", ["decision"])


def downgrade() -> None:
    """Remove review records without changing artifact objects."""
    op.drop_index("ix_artifact_reviews_decision", table_name="artifact_reviews")
    op.drop_index("ix_artifact_reviews_artifact_id", table_name="artifact_reviews")
    op.drop_table("artifact_reviews")
