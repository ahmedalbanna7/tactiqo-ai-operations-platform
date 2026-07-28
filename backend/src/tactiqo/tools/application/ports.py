"""Contracts for MCP tools and approval persistence."""

from typing import Any, Protocol
from uuid import UUID

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ApprovalRequest, ApprovalStatus, ToolDefinition, ToolResult


class ToolGateway(Protocol):
    """Discover and invoke tools without leaking MCP SDK types."""

    async def list_tools(self) -> list[ToolDefinition]:
        """Return the normalized tool catalogue."""

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Call one approved tool and return bounded untrusted content."""


class ApprovalRepository(Protocol):
    """Persist and decide human approval requests."""

    async def create(
        self,
        run_id: UUID,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ApprovalRequest:
        """Create one pending approval idempotently per tool call."""

    async def get(self, approval_id: UUID) -> ApprovalRequest | None:
        """Get an approval by opaque identifier."""

    async def find_for_call(self, run_id: UUID, tool_call_id: str) -> ApprovalRequest | None:
        """Find an existing approval for resume-safe execution."""

    async def decide(
        self,
        approval_id: UUID,
        status: ApprovalStatus,
        decided_by: str,
    ) -> ApprovalRequest | None:
        """Apply an immutable first decision."""


class ToolAuditPort(Protocol):
    """Append sanitized lifecycle events for every attempted tool action."""

    async def record(  # noqa: PLR0913 - append-only audit contract
        self,
        *,
        run_id: UUID,
        tool_call_id: str,
        tool_name: str,
        phase: str,
        safe_payload: dict[str, Any],
        context: ExecutionContext,
    ) -> None:
        """Persist one append-only tool audit event."""
