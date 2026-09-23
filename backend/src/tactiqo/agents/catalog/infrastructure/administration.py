"""PostgreSQL Agent Catalog lifecycle persistence."""

import json
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.agents.catalog.application.administration import (
    AgentApprovalChainInput,
    AgentAssignmentDetail,
    AgentAssignmentInput,
    AgentCatalogItem,
)
from tactiqo.agents.catalog.infrastructure.tables import (
    AgentActionGrantRow,
    AgentApprovalChainRow,
    AgentAssignmentRow,
    AgentAttachmentRow,
    AgentDefinitionRow,
    AgentVersionRow,
    OrganizationAgentRow,
)
from tactiqo.identity.infrastructure.tables import (
    AuthAuditRow,
    DepartmentRow,
    OrganizationMemberRow,
    OrganizationRow,
    ProjectRow,
    RoleDefinitionRow,
    TeamRow,
)

type AgentCatalogRow = tuple[AgentDefinitionRow, AgentVersionRow, OrganizationAgentRow | None]


class SqlAgentCatalogAdministrationRepository:
    """Mutate only exact-tenant records and invalidate decisions by version."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure transaction factory."""
        self._sessions = sessions

    async def list_assignments(self, organization_id: str) -> list[AgentAssignmentDetail]:
        """List only this tenant's assignments, without secrets or hidden source metadata."""
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(AgentAssignmentRow)
                    .where(AgentAssignmentRow.organization_id == organization_id)
                    .order_by(AgentAssignmentRow.created_at.desc())
                    .limit(500)
                )
            ).all()
            if not rows:
                return []
            grants = (
                await session.scalars(
                    select(AgentActionGrantRow).where(
                        AgentActionGrantRow.organization_id == organization_id,
                        AgentActionGrantRow.assignment_id.in_([row.id for row in rows]),
                    )
                )
            ).all()
            by_assignment: dict[UUID, list[AgentActionGrantRow]] = {}
            for grant in grants:
                by_assignment.setdefault(grant.assignment_id, []).append(grant)
            return [
                AgentAssignmentDetail(
                    id=row.id,
                    agent_code=row.agent_code,
                    target_type=row.target_type,
                    target_id=row.target_id,
                    actions=tuple(sorted(grant.action for grant in by_assignment.get(row.id, []))),
                    effect=(
                        by_assignment[row.id][0].effect
                        if by_assignment.get(row.id)
                        else "deny"
                    ),
                    classification_ceiling=row.classification_ceiling,
                    active=row.active,
                )
                for row in rows
            ]

    async def list_catalog(self, organization_id: str) -> list[AgentCatalogItem]:
        """Return safe definitions and available versions, bounded to this tenant's installs."""
        async with self._sessions() as session:
            rows = (await session.execute(
                select(AgentDefinitionRow, AgentVersionRow, OrganizationAgentRow)
                .join(AgentVersionRow, AgentVersionRow.agent_code == AgentDefinitionRow.code)
                .outerjoin(
                    OrganizationAgentRow,
                    (OrganizationAgentRow.agent_code == AgentDefinitionRow.code)
                    & (OrganizationAgentRow.organization_id == organization_id),
                )
                .order_by(AgentDefinitionRow.name, AgentVersionRow.created_at.desc())
                .limit(2000)
            )).all()
        grouped: dict[str, list[AgentCatalogRow]] = {}
        for definition, version, installed in rows:
            grouped.setdefault(definition.code, []).append((definition, version, installed))
        catalog: list[AgentCatalogItem] = []
        for entries in grouped.values():
            definition = entries[0][0]
            installed = next((entry[2] for entry in entries if entry[2] is not None), None)
            latest = entries[0][1]
            selected_version = installed.version if installed is not None else latest.version
            catalog.append(AgentCatalogItem(
                code=definition.code,
                name=definition.name,
                description=definition.description,
                category=definition.category,
                selected_version=selected_version,
                versions=tuple(dict.fromkeys(entry[1].version for entry in entries)),
                installed=installed is not None,
                enabled=installed.enabled if installed is not None else False,
            ))
        return catalog

    async def install(
        self, organization_id: str, agent_code: str, version: str, actor_id: UUID
    ) -> None:
        """Install a valid immutable version disabled by default."""
        async with self._sessions() as session, session.begin():
            if await session.get(AgentVersionRow, (agent_code, version)) is None:
                raise ValueError
            row = await session.get(OrganizationAgentRow, (organization_id, agent_code))
            if row is None:
                session.add(
                    OrganizationAgentRow(
                        organization_id=organization_id,
                        agent_code=agent_code,
                        version=version,
                        enabled=False,
                        installed_by=actor_id,
                    )
                )
            else:
                before = f"version={row.version};enabled={row.enabled}"
                row.version = version
                row.enabled = False
            if row is None:
                before = "absent"
            session.add(
                AuthAuditRow(
                    event_type="agent.installed",
                    user_id=actor_id,
                    organization_id=organization_id,
                    correlation_id=agent_code,
                    safe_detail=f"before={before};after=version={version};enabled=false",
                )
            )
            await self._bump_policy(session, organization_id)

    async def set_enabled(self, organization_id: str, agent_code: str, *, enabled: bool) -> bool:
        """Set installed lifecycle state with an exact tenant predicate."""
        async with self._sessions() as session, session.begin():
            row = await session.get(OrganizationAgentRow, (organization_id, agent_code))
            if row is None:
                return False
            before = row.enabled
            row.enabled = enabled
            session.add(
                AuthAuditRow(
                    event_type="agent.lifecycle.changed",
                    organization_id=organization_id,
                    correlation_id=agent_code,
                    safe_detail=f"before={before};after={enabled}",
                )
            )
            await self._bump_policy(session, organization_id)
            return True

    async def assign(
        self,
        organization_id: str,
        command: AgentAssignmentInput,
        actor_id: UUID,
    ) -> UUID:
        """Validate the relationship and persist separate grants and attachments."""
        async with self._sessions() as session, session.begin():
            installed = await session.get(
                OrganizationAgentRow, (organization_id, command.agent_code)
            )
            if installed is None:
                raise ValueError
            await self._validate_target(
                session, organization_id, command.target_type, command.target_id
            )
            row = AgentAssignmentRow(
                organization_id=organization_id,
                agent_code=command.agent_code,
                target_type=command.target_type,
                target_id=command.target_id,
                classification_ceiling=command.classification_ceiling,
                data_domains_json=json.dumps(command.data_domains),
                quota_json=json.dumps(command.quota, separators=(",", ":")),
                budget_json=json.dumps(command.budget, separators=(",", ":")),
                assigned_by=actor_id,
            )
            session.add(row)
            await session.flush()
            obligations = json.dumps(
                [{"kind": item.kind.value, "value": item.value} for item in command.obligations],
                separators=(",", ":"),
            )
            for action in command.actions:
                session.add(
                    AgentActionGrantRow(
                        organization_id=organization_id,
                        assignment_id=row.id,
                        action=action.value,
                        effect=command.effect.value,
                        obligations_json=obligations,
                    )
                )
            for kind, values in (
                ("data_domain", command.data_domains),
                ("connection", command.connection_ids),
                ("tool", command.tool_names),
            ):
                for value in values:
                    session.add(
                        AgentAttachmentRow(
                            organization_id=organization_id,
                            assignment_id=row.id,
                            attachment_type=kind,
                            reference_id=value,
                        )
                    )
            await self._bump_policy(session, organization_id)
            session.add(
                AuthAuditRow(
                    event_type="agent.assignment.created",
                    user_id=actor_id,
                    organization_id=organization_id,
                    correlation_id=str(row.id),
                    safe_detail=(
                        f"agent={command.agent_code};target_type={command.target_type};"
                        f"effect={command.effect.value};actions={len(command.actions)}"
                    ),
                )
            )
            return row.id

    async def revoke_assignment(self, organization_id: str, assignment_id: UUID) -> bool:
        """Deactivate one assignment immediately without leaking foreign IDs."""
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(AgentAssignmentRow)
                .where(
                    AgentAssignmentRow.organization_id == organization_id,
                    AgentAssignmentRow.id == assignment_id,
                    AgentAssignmentRow.active.is_(True),
                )
                .values(active=False)
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                return False
            session.add(
                AuthAuditRow(
                    event_type="agent.assignment.revoked",
                    organization_id=organization_id,
                    correlation_id=str(assignment_id),
                    safe_detail="before=active;after=revoked",
                )
            )
            await self._bump_policy(session, organization_id)
            return True

    async def set_approval_chain(
        self,
        organization_id: str,
        command: AgentApprovalChainInput,
        actor_id: UUID,
    ) -> UUID:
        """Replace an exact selector atomically and record only safe audit metadata."""
        async with self._sessions() as session, session.begin():
            if (
                await session.get(OrganizationAgentRow, (organization_id, command.agent_code))
                is None
            ):
                raise ValueError
            existing = await session.scalar(
                select(AgentApprovalChainRow).where(
                    AgentApprovalChainRow.organization_id == organization_id,
                    AgentApprovalChainRow.agent_code == command.agent_code,
                    AgentApprovalChainRow.action == command.action.value,
                    AgentApprovalChainRow.risk == command.risk,
                    AgentApprovalChainRow.target_system == command.target_system,
                )
            )
            chain_json = json.dumps(command.approver_steps, separators=(",", ":"))
            if existing is None:
                existing = AgentApprovalChainRow(
                    organization_id=organization_id,
                    agent_code=command.agent_code,
                    action=command.action.value,
                    risk=command.risk,
                    target_system=command.target_system,
                    chain_json=chain_json,
                )
                session.add(existing)
                await session.flush()
            else:
                existing.chain_json = chain_json
            await self._bump_policy(session, organization_id)
            session.add(
                AuthAuditRow(
                    event_type="agent.approval_chain.configured",
                    user_id=actor_id,
                    organization_id=organization_id,
                    correlation_id=str(existing.id),
                    safe_detail=(
                        f"agent={command.agent_code};action={command.action.value};"
                        f"risk={command.risk};target={command.target_system};"
                        f"steps={len(command.approver_steps)}"
                    ),
                )
            )
            return existing.id

    @staticmethod
    async def _validate_target(
        session: AsyncSession, organization_id: str, kind: str, target_id: str
    ) -> None:
        if kind == "organization":
            exists = target_id == organization_id
        elif kind == "role":
            exists = await session.get(RoleDefinitionRow, target_id) is not None
        elif kind == "user":
            exists = (
                await session.get(OrganizationMemberRow, (organization_id, UUID(target_id)))
                is not None
            )
        elif kind == "department":
            exists = (
                await session.scalar(
                    select(DepartmentRow.id).where(
                        DepartmentRow.organization_id == organization_id,
                        DepartmentRow.id == UUID(target_id),
                    )
                )
                is not None
            )
        elif kind == "team":
            exists = (
                await session.scalar(
                    select(TeamRow.id).where(
                        TeamRow.organization_id == organization_id,
                        TeamRow.id == UUID(target_id),
                    )
                )
                is not None
            )
        elif kind == "project":
            exists = (
                await session.scalar(
                    select(ProjectRow.id).where(
                        ProjectRow.organization_id == organization_id,
                        ProjectRow.id == UUID(target_id),
                    )
                )
                is not None
            )
        else:
            exists = False
        if not exists:
            raise ValueError

    @staticmethod
    async def _bump_policy(session: AsyncSession, organization_id: str) -> None:
        result = await session.execute(
            update(OrganizationRow)
            .where(OrganizationRow.id == organization_id)
            .values(policy_version=str(uuid4()))
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ValueError
