"""Vendor-neutral tool, result, and approval values."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ToolRisk(StrEnum):
    """Side-effect class used by deterministic policy enforcement."""

    READ_ONLY = "read_only"
    MUTATING = "mutating"
    DESTRUCTIVE = "destructive"


class ApprovalStatus(StrEnum):
    """Lifecycle for a human tool decision."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Discovered tool contract normalized from MCP."""

    name: str
    description: str
    input_schema: dict[str, Any]
    risk: ToolRisk
    server_label: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Model-proposed tool invocation before policy and execution."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Bounded, untrusted tool output."""

    call_id: str
    name: str
    content: str
    is_error: bool


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Durable approval for a mutating tool call."""

    id: UUID
    run_id: UUID
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ApprovalStatus
    actor_id: str
    organization_id: str
    created_at: datetime
    decided_at: datetime | None
