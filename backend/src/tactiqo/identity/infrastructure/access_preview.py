"""Tenant-safe organizational unit metadata for non-persistent access previews."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.authorization.domain.models import OrganizationUnitScope
from tactiqo.identity.infrastructure.tables import DepartmentRow, ProjectRow, TeamRow


class SqlAccessPreviewUnitReader:
    """Resolve active unit hierarchy using exact tenant predicates and minimal fields."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the transaction factory used for read-only lookups."""
        self._sessions = sessions

    async def read_unit(
        self, organization_id: str, kind: str, unit_id: str
    ) -> OrganizationUnitScope | None:
        """Read only IDs needed to verify a simulated membership change."""
        async with self._sessions() as session:
            if kind == "department":
                result = await self._department_scope(session, organization_id, unit_id)
            elif kind == "team":
                result = await self._team_scope(session, organization_id, unit_id)
            elif kind == "project":
                result = await self._project_scope(session, organization_id, unit_id)
            else:
                result = None
        return result

    @staticmethod
    async def _department_scope(
        session: AsyncSession, organization_id: str, unit_id: str
    ) -> OrganizationUnitScope | None:
        """Return one active department and its tenant-scoped child IDs."""
        department = await session.scalar(
            select(DepartmentRow.id).where(
                DepartmentRow.organization_id == organization_id,
                DepartmentRow.id == unit_id,
                DepartmentRow.status == "active",
            )
        )
        if department is None:
            return None
        team_ids = (
            await session.scalars(
                select(TeamRow.id).where(
                    TeamRow.organization_id == organization_id,
                    TeamRow.department_id == department,
                )
            )
        ).all()
        project_ids = (
            await session.scalars(
                select(ProjectRow.id).where(
                    ProjectRow.organization_id == organization_id,
                    ProjectRow.department_id == department,
                )
            )
        ).all()
        return OrganizationUnitScope(
            "department",
            str(department),
            str(department),
            tuple(str(value) for value in team_ids),
            tuple(str(value) for value in project_ids),
        )

    @staticmethod
    async def _team_scope(
        session: AsyncSession, organization_id: str, unit_id: str
    ) -> OrganizationUnitScope | None:
        """Return the active team identity and owning department."""
        row = await session.execute(
            select(TeamRow.id, TeamRow.department_id).where(
                TeamRow.organization_id == organization_id,
                TeamRow.id == unit_id,
                TeamRow.status == "active",
            )
        )
        result = row.one_or_none()
        if result is None:
            return None
        return OrganizationUnitScope("team", str(result.id), str(result.department_id))

    @staticmethod
    async def _project_scope(
        session: AsyncSession, organization_id: str, unit_id: str
    ) -> OrganizationUnitScope | None:
        """Return the active project identity and owning department."""
        row = await session.execute(
            select(ProjectRow.id, ProjectRow.department_id).where(
                ProjectRow.organization_id == organization_id,
                ProjectRow.id == unit_id,
                ProjectRow.status == "active",
            )
        )
        result = row.one_or_none()
        if result is None:
            return None
        return OrganizationUnitScope("project", str(result.id), str(result.department_id))
