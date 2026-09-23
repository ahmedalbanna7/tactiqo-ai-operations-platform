"""Tenant-predicated SQL Agent Catalog projection."""

import json

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Select

from tactiqo.agents.catalog.domain.models import (
    AgentCandidate,
    AgentCategory,
    AgentDefinition,
    AgentRisk,
    AgentVersion,
)
from tactiqo.agents.catalog.infrastructure.tables import (
    AgentDefinitionRow,
    AgentVersionRow,
    OrganizationAgentRow,
)


class SqlAgentCatalogRepository:
    """Load only enabled agents inside the caller's organization."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure transaction factory."""
        self._sessions = sessions

    async def list_candidates(self, organization_id: str) -> list[AgentCandidate]:
        """Load enabled installed versions without assignment metadata."""
        async with self._sessions() as session:
            rows = (await session.execute(self._query(organization_id))).all()
        return [self._map(*row) for row in rows]

    async def get_candidate(self, organization_id: str, agent_code: str) -> AgentCandidate | None:
        """Return an exact tenant candidate or the same absent shape for hidden IDs."""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    self._query(organization_id).where(AgentDefinitionRow.code == agent_code)
                )
            ).one_or_none()
        return self._map(*row) if row else None

    @staticmethod
    def _query(
        organization_id: str,
    ) -> Select[tuple[AgentDefinitionRow, AgentVersionRow]]:
        return (
            select(AgentDefinitionRow, AgentVersionRow)
            .join(
                OrganizationAgentRow,
                and_(
                    OrganizationAgentRow.agent_code == AgentDefinitionRow.code,
                    OrganizationAgentRow.organization_id == organization_id,
                    OrganizationAgentRow.enabled.is_(True),
                ),
            )
            .join(
                AgentVersionRow,
                and_(
                    AgentVersionRow.agent_code == OrganizationAgentRow.agent_code,
                    AgentVersionRow.version == OrganizationAgentRow.version,
                ),
            )
        )

    @staticmethod
    def _map(definition: AgentDefinitionRow, version: AgentVersionRow) -> AgentCandidate:
        return AgentCandidate(
            AgentDefinition(
                definition.code,
                definition.name,
                definition.description,
                AgentCategory(definition.category),
            ),
            AgentVersion(
                definition.code,
                version.version,
                version.prompt_template,
                json.loads(version.configuration_json),
                tuple(json.loads(version.capabilities_json)),
                json.loads(version.input_schema_json),
                json.loads(version.output_schema_json),
                AgentRisk(version.risk),
            ),
        )
