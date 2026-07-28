"""Deterministic tool risk and approval policy."""

from tactiqo.tools.domain.models import ToolDefinition, ToolRisk


class ToolPolicy:
    """Classify tools independently of model claims or prompt content."""

    def __init__(self, mutating_tools: frozenset[str] | None = None) -> None:
        """Configure names that are always treated as mutating."""
        self._mutating_tools = mutating_tools or frozenset({"create_follow_up_task"})

    def classify(self, name: str, *, read_only_hint: bool | None = None) -> ToolRisk:
        """Return a fail-safe risk level for a discovered tool."""
        if name in self._mutating_tools:
            return ToolRisk.MUTATING
        if read_only_hint is True:
            return ToolRisk.READ_ONLY
        return ToolRisk.MUTATING

    @staticmethod
    def requires_approval(tool: ToolDefinition) -> bool:
        """Require human approval for every non-read-only tool."""
        return tool.risk is not ToolRisk.READ_ONLY
