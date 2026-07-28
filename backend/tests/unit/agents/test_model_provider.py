"""Unit tests for the transparent local model provider."""

import asyncio

from tactiqo.agents.infrastructure.model_providers import DeterministicModelProvider
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ToolDefinition, ToolResult, ToolRisk


def _context() -> ExecutionContext:
    return ExecutionContext(
        actor_id="actor",
        organization_id="organization",
        correlation_id="correlation",
        classification_clearance="internal",
        policy_version="test-v1",
    )


def _tool(name: str, risk: ToolRisk) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=name,
        input_schema={"type": "object"},
        risk=risk,
        server_label="test",
    )


def test_provider_selects_read_only_project_tool() -> None:
    """Arabic project status intent maps to the discovered read tool."""
    turn = asyncio.run(
        DeterministicModelProvider().plan(
            "اعرض حالة المشروع",
            [],
            [_tool("get_project_snapshot", ToolRisk.READ_ONLY)],
            _context(),
        )
    )

    assert turn.tool_calls[0].name == "get_project_snapshot"


def test_provider_selects_mutation_without_executing_it() -> None:
    """The provider proposes a write while policy remains execution authority."""
    turn = asyncio.run(
        DeterministicModelProvider().plan(
            "أنشئ مهمة متابعة للفريق",
            [],
            [_tool("create_follow_up_task", ToolRisk.MUTATING)],
            _context(),
        )
    )

    assert turn.tool_calls[0].name == "create_follow_up_task"


def test_provider_formats_demo_tool_result_for_people() -> None:
    """Known tool JSON is not exposed as a raw blob in the chat experience."""
    response = asyncio.run(
        DeterministicModelProvider().answer(
            "ما هي البنود المتأخرة؟",
            [],
            [
                ToolResult(
                    call_id="call-1",
                    name="list_overdue_items",
                    content=('{"items":[{"id":"F1-17","title":"Review flow","days_overdue":1}]}'),
                    is_error=False,
                )
            ],
            _context(),
        )
    )

    assert "F1-17 — Review flow" in response
    assert '"items"' not in response
