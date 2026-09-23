"""SQL repository applying tenant predicates before returning connections."""

from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.integrations.domain.models import (
    ConnectionScope,
    ConnectionStatus,
    ConnectionToolGrant,
    GrantSubjectType,
    IntegrationConnection,
    IntegrationProvider,
    ResolvedConnection,
    ToolPermission,
)
from tactiqo.integrations.infrastructure.tables import (
    ConnectionToolGrantRow,
    IntegrationConnectionRow,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import session_scope

MAX_ACTIVE_METADATA_QUERY_LIMIT = 101


class SqlAlchemyIntegrationConnectionRepository:
    """Persist and resolve tenant-scoped integration connections."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the transaction factory."""
        self._sessions = sessions

    async def create(  # noqa: PLR0913 - mirrors explicit application port
        self,
        *,
        provider: IntegrationProvider,
        name: str,
        endpoint_url: str,
        scope: ConnectionScope,
        encrypted_authorization: str,
        context: ExecutionContext,
    ) -> IntegrationConnection:
        """Create a connection inside the caller's organization."""
        row = IntegrationConnectionRow(
            provider=provider.value,
            name=name,
            endpoint_url=endpoint_url,
            scope=scope.value,
            status=ConnectionStatus.ACTIVE.value,
            encrypted_authorization=encrypted_authorization,
            organization_id=context.organization_id,
            owner_actor_id=context.actor_id if scope is ConnectionScope.PERSONAL else None,
            created_by=context.actor_id,
        )
        async with session_scope(self._sessions) as session:
            session.add(row)
            await session.flush()
            await session.refresh(row)
        return self._model(row)

    async def list_visible(self, context: ExecutionContext) -> list[IntegrationConnection]:
        """List rows visible to the caller without encrypted credentials."""
        statement = self._visible(select(IntegrationConnectionRow), context).order_by(
            IntegrationConnectionRow.created_at.desc()
        )
        async with self._sessions() as session:
            rows = list((await session.scalars(statement)).all())
        return [self._model(row) for row in rows]

    async def list_active_metadata(
        self, context: ExecutionContext, limit: int
    ) -> list[IntegrationConnection]:
        """Return bounded active connection metadata without selecting credential material."""
        if not 1 <= limit <= MAX_ACTIVE_METADATA_QUERY_LIMIT:
            message = (
                "Connection metadata limit must be between 1 and "
                f"{MAX_ACTIVE_METADATA_QUERY_LIMIT}."
            )
            raise ValueError(message)
        statement = select(
            IntegrationConnectionRow.id,
            IntegrationConnectionRow.provider,
            IntegrationConnectionRow.name,
            IntegrationConnectionRow.endpoint_url,
            IntegrationConnectionRow.scope,
            IntegrationConnectionRow.status,
            IntegrationConnectionRow.organization_id,
            IntegrationConnectionRow.owner_actor_id,
            IntegrationConnectionRow.created_by,
            IntegrationConnectionRow.created_at,
            IntegrationConnectionRow.updated_at,
        ).where(
            IntegrationConnectionRow.organization_id == context.organization_id,
            IntegrationConnectionRow.status == ConnectionStatus.ACTIVE.value,
            or_(
                IntegrationConnectionRow.scope == ConnectionScope.ORGANIZATION.value,
                IntegrationConnectionRow.owner_actor_id == context.actor_id,
            ),
        )
        statement = statement.order_by(IntegrationConnectionRow.created_at.desc()).limit(limit)
        async with self._sessions() as session:
            rows = list((await session.execute(statement)).all())
        return [
            IntegrationConnection(
                id=row.id,
                provider=IntegrationProvider(row.provider),
                name=row.name,
                endpoint_url=row.endpoint_url,
                scope=ConnectionScope(row.scope),
                status=ConnectionStatus(row.status),
                organization_id=row.organization_id,
                owner_actor_id=row.owner_actor_id,
                created_by=row.created_by,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def list_active(self, context: ExecutionContext) -> list[ResolvedConnection]:
        """List visible active rows for per-request gateway composition."""
        statement = self._visible(select(IntegrationConnectionRow), context).where(
            IntegrationConnectionRow.status == ConnectionStatus.ACTIVE.value
        )
        async with self._sessions() as session:
            rows = list((await session.scalars(statement)).all())
        return [self._resolved(row) for row in rows]

    async def get_active(
        self,
        connection_id: UUID,
        context: ExecutionContext,
    ) -> ResolvedConnection | None:
        """Get one visible active row without cross-tenant existence leakage."""
        statement = self._visible(select(IntegrationConnectionRow), context).where(
            IntegrationConnectionRow.id == connection_id,
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        return self._resolved(row) if row is not None else None

    async def disable(
        self,
        connection_id: UUID,
        context: ExecutionContext,
    ) -> IntegrationConnection | None:
        """Disable one visible row under a lock."""
        statement = self._visible(select(IntegrationConnectionRow), context).where(
            IntegrationConnectionRow.id == connection_id
        )
        async with session_scope(self._sessions) as session:
            row = await session.scalar(statement.with_for_update())
            if row is None:
                return None
            row.status = ConnectionStatus.DISABLED.value
            row.encrypted_authorization = ""
            await session.flush()
            await session.refresh(row)
        return self._model(row)

    async def replace_credential(
        self,
        connection_id: UUID,
        encrypted_authorization: str,
        context: ExecutionContext,
    ) -> bool:
        """Rotate one credential while retaining tenant and owner predicates."""
        statement = self._visible(select(IntegrationConnectionRow), context).where(
            IntegrationConnectionRow.id == connection_id,
            IntegrationConnectionRow.status == ConnectionStatus.ACTIVE.value,
        )
        async with session_scope(self._sessions) as session:
            row = await session.scalar(statement.with_for_update())
            if row is None:
                return False
            row.encrypted_authorization = encrypted_authorization
            row.status = ConnectionStatus.ACTIVE.value
            await session.flush()
        return True

    async def mark_status(
        self, connection_id: UUID, status: ConnectionStatus, context: ExecutionContext
    ) -> IntegrationConnection | None:
        """Persist an explicit lifecycle state under tenant and owner predicates."""
        statement = self._visible(select(IntegrationConnectionRow), context).where(
            IntegrationConnectionRow.id == connection_id
        )
        async with session_scope(self._sessions) as session:
            row = await session.scalar(statement.with_for_update())
            if row is None:
                return None
            row.status = status.value
            if status in {ConnectionStatus.REVOKED, ConnectionStatus.DISABLED}:
                row.encrypted_authorization = ""
            await session.flush()
            await session.refresh(row)
        return self._model(row)

    async def upsert_grant(  # noqa: PLR0913 - explicit policy coordinates
        self,
        connection_id: UUID,
        *,
        subject_type: GrantSubjectType,
        subject_id: str,
        tool_name: str,
        permission: ToolPermission,
        context: ExecutionContext,
    ) -> ConnectionToolGrant | None:
        """Upsert one explicit grant only inside the caller tenant."""
        async with session_scope(self._sessions) as session:
            connection = await session.scalar(
                select(IntegrationConnectionRow).where(
                    IntegrationConnectionRow.id == connection_id,
                    IntegrationConnectionRow.organization_id == context.organization_id,
                )
            )
            if connection is None:
                return None
            row = await session.scalar(
                select(ConnectionToolGrantRow)
                .where(
                    ConnectionToolGrantRow.connection_id == connection_id,
                    ConnectionToolGrantRow.subject_type == subject_type.value,
                    ConnectionToolGrantRow.subject_id == subject_id,
                    ConnectionToolGrantRow.tool_name == tool_name,
                )
                .with_for_update()
            )
            if row is None:
                row = ConnectionToolGrantRow(
                    connection_id=connection_id,
                    organization_id=context.organization_id,
                    subject_type=subject_type.value,
                    subject_id=subject_id,
                    tool_name=tool_name,
                    permission=permission.value,
                    created_by=context.actor_id,
                )
                session.add(row)
            else:
                row.permission = permission.value
                row.created_by = context.actor_id
            await session.flush()
            await session.refresh(row)
        return self._grant(row)

    async def list_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """List grant metadata only within the current tenant."""
        statement = (
            select(ConnectionToolGrantRow)
            .where(
                ConnectionToolGrantRow.connection_id == connection_id,
                ConnectionToolGrantRow.organization_id == context.organization_id,
            )
            .order_by(ConnectionToolGrantRow.created_at)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._grant(row) for row in rows]

    async def effective_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """Match only server-derived user and hierarchy memberships."""
        subjects = [
            and_(
                ConnectionToolGrantRow.subject_type == GrantSubjectType.ORGANIZATION.value,
                ConnectionToolGrantRow.subject_id == context.organization_id,
            ),
            and_(
                ConnectionToolGrantRow.subject_type == GrantSubjectType.USER.value,
                ConnectionToolGrantRow.subject_id == context.actor_id,
            ),
        ]
        for subject_type, identifiers in (
            (GrantSubjectType.DEPARTMENT, context.department_ids),
            (GrantSubjectType.TEAM, context.team_ids),
            (GrantSubjectType.PROJECT, context.project_ids),
        ):
            if identifiers:
                subjects.append(
                    and_(
                        ConnectionToolGrantRow.subject_type == subject_type.value,
                        ConnectionToolGrantRow.subject_id.in_(identifiers),
                    )
                )
        statement = select(ConnectionToolGrantRow).where(
            ConnectionToolGrantRow.connection_id == connection_id,
            ConnectionToolGrantRow.organization_id == context.organization_id,
            or_(*subjects),
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._grant(row) for row in rows]

    @staticmethod
    def _visible(
        statement: Select[tuple[IntegrationConnectionRow]],
        context: ExecutionContext,
    ) -> Select[tuple[IntegrationConnectionRow]]:
        return statement.where(
            IntegrationConnectionRow.organization_id == context.organization_id,
            or_(
                IntegrationConnectionRow.scope == ConnectionScope.ORGANIZATION.value,
                IntegrationConnectionRow.owner_actor_id == context.actor_id,
            ),
        )

    @staticmethod
    def _model(row: IntegrationConnectionRow) -> IntegrationConnection:
        return IntegrationConnection(
            id=row.id,
            provider=IntegrationProvider(row.provider),
            name=row.name,
            endpoint_url=row.endpoint_url,
            scope=ConnectionScope(row.scope),
            status=ConnectionStatus(row.status),
            organization_id=row.organization_id,
            owner_actor_id=row.owner_actor_id,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @classmethod
    def _resolved(cls, row: IntegrationConnectionRow) -> ResolvedConnection:
        return ResolvedConnection(cls._model(row), row.encrypted_authorization)

    @staticmethod
    def _grant(row: ConnectionToolGrantRow) -> ConnectionToolGrant:
        return ConnectionToolGrant(
            row.id,
            row.connection_id,
            row.organization_id,
            GrantSubjectType(row.subject_type),
            row.subject_id,
            row.tool_name,
            ToolPermission(row.permission),
            row.created_by,
            row.created_at,
        )
