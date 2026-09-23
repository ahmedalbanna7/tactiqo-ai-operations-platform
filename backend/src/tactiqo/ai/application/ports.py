"""Ports for AI profiles and provider adapters."""

import builtins
from collections.abc import Sequence
from typing import Protocol

from tactiqo.agents.domain.models import ModelTurn
from tactiqo.ai.domain.models import EmbeddingResult, ProviderHealth, ProviderKind, ProviderProfile
from tactiqo.knowledge.domain.models import KnowledgeResult
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ToolDefinition, ToolResult


class ProviderProfileRepository(Protocol):
    """PostgreSQL-backed tenant profile boundary."""

    async def active(self, organization_id: str, kind: ProviderKind) -> ProviderProfile | None:
        """Return one active profile."""

    async def list(self, organization_id: str) -> list[ProviderProfile]:
        """List non-secret profile metadata."""

    async def enabled(
        self, organization_id: str, kind: ProviderKind
    ) -> builtins.list[ProviderProfile]:
        """List enabled profiles for bounded capability routing."""

    async def upsert(self, organization_id: str, profile: ProviderProfile, actor_id: str) -> None:
        """Persist and activate one validated profile."""

    async def disable(self, organization_id: str, name: str, actor_id: str) -> bool:
        """Disable one tenant profile without affecting other providers."""

    async def account(
        self, organization_id: str, profile: str, latency_ms: int, units: int, error: str | None
    ) -> None:
        """Persist sanitized usage accounting."""


class AISecretStore(Protocol):
    """Write-only provider credential storage behind an opaque reference."""

    async def put(self, organization_id: str, provider: str, secret: str, actor_id: str) -> str:
        """Encrypt a secret and return an opaque non-secret reference."""

    async def resolve(self, reference: str) -> str | None:
        """Resolve active provider material only inside infrastructure code."""

    async def belongs_to(self, reference: str, organization_id: str, provider: str) -> bool:
        """Validate tenant and provider ownership before binding a profile."""


class EmbeddingAdapter(Protocol):
    """Provider-neutral embedding adapter."""

    async def embed(self, texts: Sequence[str], profile: ProviderProfile) -> EmbeddingResult:
        """Embed one bounded batch."""

    async def health(self, profile: ProviderProfile) -> ProviderHealth:
        """Test endpoint and discover model identifiers."""

    async def prepare(self, profile: ProviderProfile) -> ProviderHealth:
        """Make the selected model ready before atomically activating it."""


class LLMAdapter(Protocol):
    """Complete LLM contract implemented only by infrastructure adapters."""

    async def plan(
        self,
        message: str,
        evidence: Sequence[KnowledgeResult],
        tools: Sequence[ToolDefinition],
        context: ExecutionContext,
        profile: ProviderProfile,
    ) -> ModelTurn:
        """Return a bounded text or tool-call turn."""

    async def answer(
        self,
        message: str,
        evidence: Sequence[KnowledgeResult],
        tool_results: Sequence[ToolResult],
        context: ExecutionContext,
        profile: ProviderProfile,
    ) -> str:
        """Return grounded user-facing text."""

    async def health(self, profile: ProviderProfile) -> ProviderHealth:
        """Test endpoint and discover models."""

    async def prepare(self, profile: ProviderProfile) -> ProviderHealth:
        """Make the selected model ready before atomically activating it."""
