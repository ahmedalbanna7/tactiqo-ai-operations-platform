"""Authorization ports used before retrieval, tools, and persistence."""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from tactiqo.shared.domain.execution import ExecutionContext


class ProtectedAction(StrEnum):
    """Actions that require a policy decision."""

    CHAT = "chat"
    RETRIEVE = "retrieve"
    TOOL_READ = "tool.read"
    TOOL_WRITE = "tool.write"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_REVOKE = "document.revoke"


class AuthorizationDecision(BaseModel):
    """Fail-closed result from an authorization provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    reason_code: str
    requires_approval: bool = False


class AuthorizationPort(Protocol):
    """Evaluate an action for a server-derived execution context."""

    async def authorize(
        self,
        context: ExecutionContext,
        action: ProtectedAction,
        resource_id: str | None = None,
    ) -> AuthorizationDecision:
        """Return a policy decision without leaking resource existence."""


class LocalDevelopmentAuthorization:
    """Explicitly local policy adapter used until Phase 1 identity is activated."""

    async def authorize(
        self,
        context: ExecutionContext,
        action: ProtectedAction,
        resource_id: str | None = None,
    ) -> AuthorizationDecision:
        """Allow the local principal while requiring approval for mutations."""
        del context, resource_id
        return AuthorizationDecision(
            allowed=True,
            reason_code="local_development_policy",
            requires_approval=action is ProtectedAction.TOOL_WRITE,
        )
