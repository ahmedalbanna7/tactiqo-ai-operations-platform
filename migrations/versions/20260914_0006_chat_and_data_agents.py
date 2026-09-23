"""Add least-privileged chat and structured-data specialist agents.

Revision ID: 20260914_0006
Revises: 20260914_0005
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0006"
down_revision: str | Sequence[str] | None = "20260914_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENTS = (
    (
        "chat_assistant",
        "Chat Assistant",
        "Handles authorized conversational requests without unnecessary planning.",
        "coordination",
        "low",
    ),
    (
        "data_analytics",
        "Data & Analytics Agent",
        "Queries authorized SQL, NoSQL, warehouse, and analytical data tools.",
        "data_bi",
        "medium",
    ),
)


def upgrade() -> None:
    """Register immutable v1 definitions before tenant installation bootstrap."""
    definitions = sa.table(
        "agent_definitions",
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("category", sa.String()),
    )
    versions = sa.table(
        "agent_versions",
        sa.column("agent_code", sa.String()),
        sa.column("version", sa.String()),
        sa.column("prompt_template", sa.Text()),
        sa.column("configuration_json", sa.Text()),
        sa.column("capabilities_json", sa.Text()),
        sa.column("input_schema_json", sa.Text()),
        sa.column("output_schema_json", sa.Text()),
        sa.column("risk", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        definitions,
        [
            {"code": code, "name": name, "description": description, "category": category}
            for code, name, description, category, _risk in _AGENTS
        ],
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        versions,
        [
            {
                "agent_code": code,
                "version": "1.0.0",
                "prompt_template": "system-template-v1",
                "configuration_json": "{}",
                "capabilities_json": "[]",
                "input_schema_json": "{}",
                "output_schema_json": "{}",
                "risk": risk,
                "created_at": now,
            }
            for code, _name, _description, _category, risk in _AGENTS
        ],
    )


def downgrade() -> None:
    """Remove the specialist definitions when no tenant installs reference them."""
    codes = [agent[0] for agent in _AGENTS]
    op.execute(
        sa.delete(sa.table("agent_versions", sa.column("agent_code"))).where(
            sa.column("agent_code").in_(codes)
        )
    )
    op.execute(
        sa.delete(sa.table("agent_definitions", sa.column("code"))).where(
            sa.column("code").in_(codes)
        )
    )
