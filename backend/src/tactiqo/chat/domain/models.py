"""Provider-independent chat and run domain values."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class MessageRole(StrEnum):
    """Supported conversation roles persisted by the platform."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RunStatus(StrEnum):
    """Durable lifecycle for an agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        """Return whether no more events are expected for this run."""
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


class AgentEventType(StrEnum):
    """Stable event names consumed by the chat UI."""

    RUN_STARTED = "run.started"
    RUN_STEP = "run.step"
    RETRIEVAL_COMPLETED = "retrieval.completed"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_DECIDED = "approval.decided"
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETED = "message.completed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"


@dataclass(frozen=True, slots=True)
class Conversation:
    """Conversation summary scoped to one organization and actor."""

    id: UUID
    title: str
    actor_id: str
    organization_id: str
    classification: str
    policy_version: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Message:
    """One immutable conversation message."""

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRun:
    """Durable status for one user-message orchestration."""

    id: UUID
    conversation_id: UUID
    user_message_id: UUID
    status: RunStatus
    current_step: str
    cancel_requested: bool
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """Ordered, resumable event emitted during a run."""

    sequence: int
    run_id: UUID
    event_type: AgentEventType
    payload: dict[str, Any]
    created_at: datetime
