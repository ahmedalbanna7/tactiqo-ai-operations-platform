"""Persistence contracts for conversations and agent runs."""

from typing import Any, Protocol
from uuid import UUID

from tactiqo.chat.domain.models import (
    AgentEvent,
    AgentRun,
    Conversation,
    Message,
    MessageRole,
    RunStatus,
)
from tactiqo.shared.domain.execution import ExecutionContext


class ChatRepository(Protocol):
    """Store chat truth without exposing persistence-specific objects."""

    async def create_conversation(
        self,
        context: ExecutionContext,
        title: str,
    ) -> Conversation:
        """Create a scoped conversation."""

    async def list_conversations(
        self,
        context: ExecutionContext,
        limit: int = 50,
    ) -> list[Conversation]:
        """List conversations visible to the actor."""

    async def get_conversation(
        self,
        context: ExecutionContext,
        conversation_id: UUID,
    ) -> Conversation | None:
        """Get one visible conversation or return no result."""

    async def list_messages(
        self,
        context: ExecutionContext,
        conversation_id: UUID,
    ) -> list[Message]:
        """List ordered messages without cross-scope leakage."""

    async def add_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        """Append an immutable message."""

    async def create_run(self, conversation_id: UUID, user_message_id: UUID) -> AgentRun:
        """Create a queued run."""

    async def get_run(self, run_id: UUID) -> AgentRun | None:
        """Get a run by opaque identifier."""

    async def update_run(
        self,
        run_id: UUID,
        status: RunStatus,
        current_step: str,
        error_code: str | None = None,
    ) -> AgentRun:
        """Transition run status and step."""

    async def request_cancel(self, run_id: UUID) -> AgentRun | None:
        """Persist a cancellation request."""

    async def append_event(
        self,
        run_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> AgentEvent:
        """Append one ordered run event."""

    async def list_events(self, run_id: UUID, after: int = 0) -> list[AgentEvent]:
        """Return events after a client checkpoint."""
