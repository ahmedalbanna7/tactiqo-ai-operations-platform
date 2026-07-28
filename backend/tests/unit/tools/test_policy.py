"""Unit tests for deterministic MCP tool policy."""

from tactiqo.tools.application.policy import ToolPolicy
from tactiqo.tools.domain.models import ToolDefinition, ToolRisk


def test_policy_trusts_read_only_hint_only_for_known_non_mutation() -> None:
    """A read-only hint classifies a tool as safe for automatic execution."""
    policy = ToolPolicy()

    assert policy.classify("get_project_snapshot", read_only_hint=True) is ToolRisk.READ_ONLY


def test_policy_fails_unknown_tools_to_mutating() -> None:
    """Missing annotations never make an unknown tool automatically executable."""
    policy = ToolPolicy()

    assert policy.classify("unknown_tool") is ToolRisk.MUTATING


def test_mutating_tools_always_require_human_approval() -> None:
    """A mutating definition cannot bypass approval policy."""
    tool = ToolDefinition(
        name="create_follow_up_task",
        description="Create a task",
        input_schema={"type": "object"},
        risk=ToolRisk.MUTATING,
        server_label="test",
    )

    assert ToolPolicy.requires_approval(tool) is True
