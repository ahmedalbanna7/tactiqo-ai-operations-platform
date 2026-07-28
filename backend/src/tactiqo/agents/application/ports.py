"""Model-provider and orchestration contracts."""

from collections.abc import Sequence
from typing import Protocol

from tactiqo.agents.domain.models import ModelTurn
from tactiqo.knowledge.domain.models import KnowledgeResult
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ToolDefinition, ToolResult


class ModelProviderPort(Protocol):
    """Plan and synthesize without leaking provider SDK objects."""

    async def plan(
        self,
        message: str,
        evidence: Sequence[KnowledgeResult],
        tools: Sequence[ToolDefinition],
        context: ExecutionContext,
    ) -> ModelTurn:
        """Return text or structured tool calls."""

    async def answer(
        self,
        message: str,
        evidence: Sequence[KnowledgeResult],
        tool_results: Sequence[ToolResult],
        context: ExecutionContext,
    ) -> str:
        """Synthesize the final grounded user-facing answer."""
