"""SQLAlchemy approval repository with immutable first-decision semantics."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import session_scope
from tactiqo.tools.domain.models import ApprovalRequest, ApprovalStatus
from tactiqo.tools.infrastructure.tables import ApprovalRequestRow, ToolAuditRow


class SqlAlchemyApprovalRepository:
    """Persist tool approvals independently from the orchestration runtime."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the repository with a transaction factory."""
        self._sessions = sessions

    async def create(
        self,
        run_id: UUID,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ApprovalRequest:
        """Create or return the approval for a resume-safe tool call."""
        existing = await self.find_for_call(run_id, tool_call_id)
        if existing is not None:
            return existing
        row = ApprovalRequestRow(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            status=ApprovalStatus.PENDING.value,
            actor_id=context.actor_id,
            organization_id=context.organization_id,
        )
        async with session_scope(self._sessions) as session:
            session.add(row)
            await session.flush()
            await session.refresh(row)
        return self._approval(row)

    async def get(self, approval_id: UUID) -> ApprovalRequest | None:
        """Get an approval without returning persistence types."""
        async with self._sessions() as session:
            row = await session.get(ApprovalRequestRow, approval_id)
        return self._approval(row) if row is not None else None

    async def find_for_call(self, run_id: UUID, tool_call_id: str) -> ApprovalRequest | None:
        """Find an approval using its run-scoped idempotency key."""
        statement = select(ApprovalRequestRow).where(
            ApprovalRequestRow.run_id == run_id,
            ApprovalRequestRow.tool_call_id == tool_call_id,
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        return self._approval(row) if row is not None else None

    async def decide(
        self,
        approval_id: UUID,
        status: ApprovalStatus,
        decided_by: str,
    ) -> ApprovalRequest | None:
        """Record only the first human decision for an approval request."""
        async with session_scope(self._sessions) as session:
            row = await session.get(ApprovalRequestRow, approval_id, with_for_update=True)
            if row is None:
                return None
            if row.status == ApprovalStatus.PENDING.value:
                row.status = status.value
                row.decided_by = decided_by
                row.decided_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(row)
        return self._approval(row)

    @staticmethod
    def _approval(row: ApprovalRequestRow) -> ApprovalRequest:
        return ApprovalRequest(
            id=row.id,
            run_id=row.run_id,
            tool_call_id=row.tool_call_id,
            tool_name=row.tool_name,
            arguments=row.arguments,
            status=ApprovalStatus(row.status),
            actor_id=row.actor_id,
            organization_id=row.organization_id,
            created_at=row.created_at,
            decided_at=row.decided_at,
        )


class SqlAlchemyToolAuditRepository:
    """Append sanitized tool lifecycle records without storing model internals."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the append-only audit repository."""
        self._sessions = sessions

    async def record(  # noqa: PLR0913 - append-only audit persistence contract
        self,
        *,
        run_id: UUID,
        tool_call_id: str,
        tool_name: str,
        phase: str,
        safe_payload: dict[str, Any],
        context: ExecutionContext,
    ) -> None:
        """Persist a bounded append-only audit event."""
        row = ToolAuditRow(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            phase=phase[:32],
            safe_payload=safe_payload,
            actor_id=context.actor_id,
            organization_id=context.organization_id,
            correlation_id=context.correlation_id,
        )
        async with session_scope(self._sessions) as session:
            session.add(row)
