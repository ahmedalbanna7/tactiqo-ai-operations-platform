"""Application use cases for scoped conversations and agent runs."""

from uuid import UUID

from tactiqo.agents.application.supervisor import AgentTaskSupervisor
from tactiqo.chat.application.ports import ChatRepository
from tactiqo.chat.domain.models import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    Conversation,
    Message,
    MessageRole,
    RunStatus,
)
from tactiqo.shared.application.authorization import AuthorizationPort, ProtectedAction
from tactiqo.shared.domain.execution import ExecutionContext


class ChatService:
    """Coordinate chat persistence, authorization, and background execution."""

    def __init__(
        self,
        repository: ChatRepository,
        authorization: AuthorizationPort,
        supervisor: AgentTaskSupervisor,
    ) -> None:
        """Configure persistence, policy, and execution scheduling."""
        self._repository = repository
        self._authorization = authorization
        self._supervisor = supervisor

    async def create_conversation(
        self,
        context: ExecutionContext,
        title: str,
    ) -> Conversation:
        """Create a conversation after the chat policy gate."""
        await self._require(context, ProtectedAction.CHAT)
        return await self._repository.create_conversation(context, title.strip()[:160])

    async def list_conversations(self, context: ExecutionContext) -> list[Conversation]:
        """List only conversations in the server-derived scope."""
        await self._require(context, ProtectedAction.CHAT)
        return await self._repository.list_conversations(context)

    async def list_messages(
        self,
        context: ExecutionContext,
        conversation_id: UUID,
    ) -> list[Message] | None:
        """Return messages only when their parent conversation is visible."""
        if await self._repository.get_conversation(context, conversation_id) is None:
            return None
        return await self._repository.list_messages(context, conversation_id)

    async def send_message(
        self,
        context: ExecutionContext,
        conversation_id: UUID,
        content: str,
    ) -> AgentRun | None:
        """Persist the user message and start one bounded agent run."""
        await self._require(context, ProtectedAction.CHAT)
        if await self._repository.get_conversation(context, conversation_id) is None:
            return None
        message = await self._repository.add_message(
            conversation_id,
            MessageRole.USER,
            content.strip(),
        )
        run = await self._repository.create_run(conversation_id, message.id)
        self._supervisor.start(run.id, message.content, context)
        return run

    async def get_run(
        self,
        context: ExecutionContext,
        run_id: UUID,
    ) -> AgentRun | None:
        """Get a run without disclosing cross-scope identifiers."""
        run = await self._repository.get_run(run_id)
        if run is None:
            return None
        visible = await self._repository.get_conversation(context, run.conversation_id)
        return run if visible is not None else None

    async def list_events(
        self,
        context: ExecutionContext,
        run_id: UUID,
        after: int,
    ) -> list[AgentEvent] | None:
        """Return resumable events after verifying run scope."""
        if await self.get_run(context, run_id) is None:
            return None
        return await self._repository.list_events(run_id, after)

    async def cancel(
        self,
        context: ExecutionContext,
        run_id: UUID,
    ) -> AgentRun | None:
        """Persist cooperative cancellation for a visible non-terminal run."""
        run = await self.get_run(context, run_id)
        if run is None:
            return None
        updated = await self._repository.request_cancel(run_id)
        if updated is not None and run.status in {RunStatus.QUEUED, RunStatus.WAITING_APPROVAL}:
            updated = await self._repository.update_run(
                run_id,
                RunStatus.CANCELLED,
                "cancelled",
            )
            await self._repository.append_event(
                run_id,
                AgentEventType.RUN_CANCELLED.value,
                {"status": "cancelled"},
            )
        return updated

    async def _require(
        self,
        context: ExecutionContext,
        action: ProtectedAction,
    ) -> None:
        decision = await self._authorization.authorize(context, action)
        if not decision.allowed:
            msg = f"Policy denied action: {decision.reason_code}"
            raise PermissionError(msg)
