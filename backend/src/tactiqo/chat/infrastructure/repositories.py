"""SQLAlchemy repository for scoped conversations and durable run events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.chat.domain.models import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    Conversation,
    Message,
    MessageRole,
    RunStatus,
)
from tactiqo.chat.infrastructure.tables import (
    AgentEventRow,
    AgentRunRow,
    ConversationRow,
    MessageRow,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import session_scope


class SqlAlchemyChatRepository:
    """Persist chat state while enforcing organization and actor scope."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the repository with a transaction factory."""
        self._sessions = sessions

    async def create_conversation(
        self,
        context: ExecutionContext,
        title: str,
    ) -> Conversation:
        """Create a conversation owned by the current local execution context."""
        row = ConversationRow(
            title=title,
            actor_id=context.actor_id,
            organization_id=context.organization_id,
            classification=context.classification_clearance,
            policy_version=context.policy_version,
        )
        async with session_scope(self._sessions) as session:
            session.add(row)
            await session.flush()
            await session.refresh(row)
        return self._conversation(row)

    async def list_conversations(
        self,
        context: ExecutionContext,
        limit: int = 50,
    ) -> list[Conversation]:
        """List recent conversations within exact organization and actor scope."""
        statement = (
            select(ConversationRow)
            .where(
                ConversationRow.organization_id == context.organization_id,
                ConversationRow.actor_id == context.actor_id,
            )
            .order_by(ConversationRow.updated_at.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._conversation(row) for row in rows]

    async def get_conversation(
        self,
        context: ExecutionContext,
        conversation_id: UUID,
    ) -> Conversation | None:
        """Get a conversation without disclosing cross-scope existence."""
        statement = select(ConversationRow).where(
            ConversationRow.id == conversation_id,
            ConversationRow.organization_id == context.organization_id,
            ConversationRow.actor_id == context.actor_id,
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        return self._conversation(row) if row is not None else None

    async def list_messages(
        self,
        context: ExecutionContext,
        conversation_id: UUID,
    ) -> list[Message]:
        """List messages only after applying the parent conversation scope."""
        statement = (
            select(MessageRow)
            .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
            .where(
                MessageRow.conversation_id == conversation_id,
                ConversationRow.organization_id == context.organization_id,
                ConversationRow.actor_id == context.actor_id,
            )
            .order_by(MessageRow.created_at, MessageRow.id)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._message(row) for row in rows]

    async def add_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        """Append a message and touch the conversation ordering timestamp."""
        now = datetime.now(UTC)
        row = MessageRow(conversation_id=conversation_id, role=role.value, content=content)
        async with session_scope(self._sessions) as session:
            session.add(row)
            conversation = await session.get(ConversationRow, conversation_id)
            if conversation is None:
                msg = "Conversation disappeared before message append."
                raise LookupError(msg)
            conversation.updated_at = now
            await session.flush()
            await session.refresh(row)
        return self._message(row)

    async def create_run(self, conversation_id: UUID, user_message_id: UUID) -> AgentRun:
        """Create a queued agent run for one immutable user message."""
        row = AgentRunRow(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            status=RunStatus.QUEUED.value,
            current_step="queued",
        )
        async with session_scope(self._sessions) as session:
            session.add(row)
            await session.flush()
            await session.refresh(row)
        return self._run(row)

    async def get_run(self, run_id: UUID) -> AgentRun | None:
        """Get a run for transport and orchestration state checks."""
        async with self._sessions() as session:
            row = await session.get(AgentRunRow, run_id)
        return self._run(row) if row is not None else None

    async def update_run(
        self,
        run_id: UUID,
        status: RunStatus,
        current_step: str,
        error_code: str | None = None,
    ) -> AgentRun:
        """Transition a run and mark terminal timestamps consistently."""
        now = datetime.now(UTC)
        async with session_scope(self._sessions) as session:
            row = await session.get(AgentRunRow, run_id, with_for_update=True)
            if row is None:
                msg = "Agent run not found."
                raise LookupError(msg)
            row.status = status.value
            row.current_step = current_step
            row.error_code = error_code
            row.updated_at = now
            row.completed_at = now if status.terminal else None
            await session.flush()
            await session.refresh(row)
        return self._run(row)

    async def request_cancel(self, run_id: UUID) -> AgentRun | None:
        """Persist cancellation intent for cooperative graph nodes."""
        async with session_scope(self._sessions) as session:
            row = await session.get(AgentRunRow, run_id, with_for_update=True)
            if row is None:
                return None
            row.cancel_requested = True
            row.updated_at = datetime.now(UTC)
            await session.flush()
            await session.refresh(row)
        return self._run(row)

    async def append_event(
        self,
        run_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> AgentEvent:
        """Append a strictly ordered event for resumable SSE clients."""
        async with session_scope(self._sessions) as session:
            await session.execute(
                select(AgentRunRow.id).where(AgentRunRow.id == run_id).with_for_update()
            )
            current = await session.scalar(
                select(func.max(AgentEventRow.sequence)).where(AgentEventRow.run_id == run_id)
            )
            row = AgentEventRow(
                run_id=run_id,
                sequence=(current or 0) + 1,
                event_type=event_type,
                payload=payload,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
        return self._event(row)

    async def list_events(self, run_id: UUID, after: int = 0) -> list[AgentEvent]:
        """Return an ordered event page after the caller's last sequence."""
        statement = (
            select(AgentEventRow)
            .where(AgentEventRow.run_id == run_id, AgentEventRow.sequence > after)
            .order_by(AgentEventRow.sequence)
            .limit(200)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._event(row) for row in rows]

    @staticmethod
    def _conversation(row: ConversationRow) -> Conversation:
        return Conversation(
            id=row.id,
            title=row.title,
            actor_id=row.actor_id,
            organization_id=row.organization_id,
            classification=row.classification,
            policy_version=row.policy_version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _message(row: MessageRow) -> Message:
        return Message(
            id=row.id,
            conversation_id=row.conversation_id,
            role=MessageRole(row.role),
            content=row.content,
            created_at=row.created_at,
        )

    @staticmethod
    def _run(row: AgentRunRow) -> AgentRun:
        return AgentRun(
            id=row.id,
            conversation_id=row.conversation_id,
            user_message_id=row.user_message_id,
            status=RunStatus(row.status),
            current_step=row.current_step,
            cancel_requested=row.cancel_requested,
            error_code=row.error_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
            completed_at=row.completed_at,
        )

    @staticmethod
    def _event(row: AgentEventRow) -> AgentEvent:
        return AgentEvent(
            sequence=row.sequence,
            run_id=row.run_id,
            event_type=AgentEventType(row.event_type),
            payload=row.payload,
            created_at=row.created_at,
        )
