"""Tenant predicates and minimal hierarchy projection for access-preview units."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast
from uuid import uuid4

import pytest

from tactiqo.authorization.domain.models import OrganizationUnitScope
from tactiqo.identity.infrastructure.access_preview import SqlAccessPreviewUnitReader

DEPARTMENT_QUERY_COUNT = 3
SINGLE_QUERY_COUNT = 1

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class FakeScalarResult:
    """Return configured rows through SQLAlchemy's scalar-result interface."""

    def __init__(self, values: list[object]) -> None:
        """Store one bounded result page."""
        self.values = values

    def all(self) -> list[object]:
        """Return the configured IDs."""
        return self.values

    def one_or_none(self) -> object | None:
        """Return the single configured row, when present."""
        return self.values[0] if self.values else None


@dataclass(frozen=True)
class FakeUnitRow:
    """Selected id/department columns returned by SQLAlchemy Core."""

    id: object
    department_id: object


class FakeSession:
    """Capture compiled query objects without requiring a database server."""

    def __init__(self) -> None:
        """Prepare one department and child-unit result set."""
        self.statements: list[object] = []
        self.scalar_value: object | None = uuid4()
        self.scalar_results: list[list[object]] = [[uuid4()], [uuid4()]]
        self.execute_value: FakeUnitRow | None = FakeUnitRow(uuid4(), uuid4())

    async def __aenter__(self) -> Self:
        """Provide the asynchronous context-manager contract."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Close the fake session without side effects."""
        _ = args

    async def scalar(self, statement: object) -> object | None:
        """Record one selected entity query."""
        self.statements.append(statement)
        return self.scalar_value

    async def scalars(self, statement: object) -> FakeScalarResult:
        """Record one descendant membership query."""
        self.statements.append(statement)
        return FakeScalarResult(self.scalar_results[len(self.statements) - 2])

    async def execute(self, statement: object) -> FakeScalarResult:
        """Record one team/project projection."""
        self.statements.append(statement)
        return FakeScalarResult([self.execute_value] if self.execute_value is not None else [])


class FakeSessionFactory:
    """Return one captured session to the SQL reader."""

    def __init__(self, session: FakeSession) -> None:
        """Store the session used to capture all statements."""
        self.session = session

    def __call__(self) -> FakeSession:
        """Return the configured asynchronous context manager."""
        return self.session


def _assert_tenant_predicates(session: FakeSession, organization_id: str) -> None:
    """Each generated read must include the exact caller tenant as a SQL bind."""
    assert session.statements
    for statement in session.statements:
        compiled = statement.compile()  # type: ignore[attr-defined]
        assert organization_id in compiled.params.values()


@pytest.mark.anyio
async def test_department_scope_reads_tenant_children_including_inactive_units() -> None:
    """Department removal gets all descendant IDs without status-based omissions."""
    session = FakeSession()
    department_id = session.scalar_value
    team_ids = session.scalar_results[0]
    project_ids = session.scalar_results[1]
    sessions = cast("async_sessionmaker[AsyncSession]", FakeSessionFactory(session))
    reader = SqlAccessPreviewUnitReader(sessions)

    result = await reader.read_unit("tenant-a", "department", str(department_id))

    assert result == OrganizationUnitScope(
        "department",
        str(department_id),
        str(department_id),
        tuple(str(value) for value in team_ids),
        tuple(str(value) for value in project_ids),
    )
    _assert_tenant_predicates(session, "tenant-a")
    assert len(session.statements) == DEPARTMENT_QUERY_COUNT
    assert "teams.status" not in str(session.statements[1])
    assert "projects.status" not in str(session.statements[2])


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["team", "project"])
async def test_child_scope_query_is_tenant_filtered(kind: str) -> None:
    """Team and project metadata reads carry the owning tenant predicate."""
    session = FakeSession()
    result_row = session.execute_value
    assert result_row is not None
    sessions = cast("async_sessionmaker[AsyncSession]", FakeSessionFactory(session))
    reader = SqlAccessPreviewUnitReader(sessions)

    result = await reader.read_unit("tenant-a", kind, str(result_row.id))

    assert result == OrganizationUnitScope(kind, str(result_row.id), str(result_row.department_id))
    _assert_tenant_predicates(session, "tenant-a")
    assert len(session.statements) == SINGLE_QUERY_COUNT


@pytest.mark.anyio
async def test_missing_department_does_not_query_children() -> None:
    """A missing or cross-tenant department returns unavailable without child reads."""
    session = FakeSession()
    session.scalar_value = None
    sessions = cast("async_sessionmaker[AsyncSession]", FakeSessionFactory(session))
    reader = SqlAccessPreviewUnitReader(sessions)

    result = await reader.read_unit("tenant-a", "department", str(uuid4()))

    assert result is None
    _assert_tenant_predicates(session, "tenant-a")
    assert len(session.statements) == SINGLE_QUERY_COUNT
