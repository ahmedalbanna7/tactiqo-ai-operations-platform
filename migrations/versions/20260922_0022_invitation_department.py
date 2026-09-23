"""Bind organization invitations to an authorized department."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0022"
down_revision: str | Sequence[str] | None = "20260921_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Require new invitations to choose a tenant-owned department."""
    op.add_column(
        "organization_invitations",
        sa.Column("department_id", sa.Uuid(), nullable=True),
    )
    op.alter_column(
        "organization_invitations", "email", existing_type=sa.String(320), nullable=True
    )
    op.create_foreign_key(
        "fk_invitation_department_id", "organization_invitations", "departments",
        ["department_id"], ["id"], ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove department binding without deleting invitation history."""
    op.execute(
        "UPDATE organization_invitations SET email = '' WHERE email IS NULL"
    )
    op.drop_constraint(
        "fk_invitation_department_id", "organization_invitations", type_="foreignkey"
    )
    op.drop_column("organization_invitations", "department_id")
    op.alter_column(
        "organization_invitations", "email", existing_type=sa.String(320), nullable=False
    )
