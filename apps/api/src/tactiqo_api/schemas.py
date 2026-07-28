"""Strict transport schemas for system and F1 functional endpoints."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    """Forbid accidental transport fields at every public boundary."""

    model_config = ConfigDict(extra="forbid")


class ComponentHealthResponse(StrictSchema):
    """Expose a safe readiness result for one dependency."""

    name: str
    status: str
    detail: str | None = None


class HealthResponse(StrictSchema):
    """Expose service liveness or aggregate readiness."""

    status: str
    service: str
    version: str
    environment: str
    components: list[ComponentHealthResponse] = Field(default_factory=list)


class ServiceInfoResponse(StrictSchema):
    """Expose non-sensitive service identity information."""

    name: str
    version: str
    environment: str


class CreateConversationRequest(StrictSchema):
    """Create a titled conversation."""

    title: str = Field(default="محادثة جديدة", min_length=1, max_length=160)


class ConversationResponse(StrictSchema):
    """Conversation summary visible in the sidebar."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(StrictSchema):
    """Persisted chat message."""

    id: UUID
    role: str
    content: str
    created_at: datetime


class SendMessageRequest(StrictSchema):
    """Submit one user turn."""

    content: str = Field(min_length=1, max_length=32_000)


class AgentRunResponse(StrictSchema):
    """Durable workflow status returned to polling and SSE clients."""

    id: UUID
    conversation_id: UUID
    status: str
    current_step: str
    cancel_requested: bool
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ApprovalDecisionRequest(StrictSchema):
    """Human decision for a material MCP action."""

    decision: Literal["approved", "rejected"]


class ApprovalResponse(StrictSchema):
    """Public state of a scoped approval request."""

    id: UUID
    run_id: UUID
    tool_name: str
    arguments: dict[str, Any]
    status: str
    created_at: datetime
    decided_at: datetime | None


class DocumentResponse(StrictSchema):
    """Canonical knowledge document processing state."""

    id: UUID
    name: str
    content_type: str
    source_uri: str
    status: str
    project_id: str | None
    parser_name: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
