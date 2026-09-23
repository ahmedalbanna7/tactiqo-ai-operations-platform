"""Tool gateway telemetry contains only fixed server-family and outcome labels."""

import asyncio
from typing import Any

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.telemetry import ToolCallMetrics
from tactiqo.tools.domain.models import ToolDefinition, ToolResult
from tactiqo.tools.infrastructure.telemetry import InstrumentedToolGateway


class StubGateway:
    """Remote-call test double returning untrusted text that must not enter metrics."""

    async def list_tools(self, _context: ExecutionContext) -> list[ToolDefinition]:
        """Return an empty catalogue for the telemetry-only test."""
        return []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        _context: ExecutionContext,
    ) -> ToolResult:
        """Echo test inputs only through the result, never through metrics."""
        return ToolResult(
            call_id="customer-call-id",
            name=name,
            content=str(arguments),
            is_error=False,
        )


def test_instrumented_gateway_preserves_result_and_redacts_call_details() -> None:
    """Success metrics use a provider family and omit remote names, args, and results."""
    metrics = ToolCallMetrics()
    gateway = InstrumentedToolGateway(StubGateway(), metrics)
    context = ExecutionContext("actor", "org", "corr", "internal", "test")
    result = asyncio.run(
        gateway.call_tool(
            "slack_connection-secret__private-method",
            {"private_argument": "sensitive-value"},
            context,
        )
    )

    rendered = metrics.render_prometheus()

    assert result.content == "{'private_argument': 'sensitive-value'}"
    assert 'tactiqo_tool_calls_total{server_family="slack",outcome="success"} 1' in rendered
    assert "connection-secret" not in rendered
    assert "private-method" not in rendered
    assert "sensitive-value" not in rendered
    assert "customer-call-id" not in rendered


def test_instrumented_gateway_records_tool_error_as_failure() -> None:
    """An MCP error result increments failure without serializing its details."""

    class FailedGateway(StubGateway):
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any],
            context: ExecutionContext,
        ) -> ToolResult:
            """Return a simulated provider error result."""
            del arguments, context
            return ToolResult("", name, "provider-secret-error", is_error=True)

    metrics = ToolCallMetrics()
    gateway = InstrumentedToolGateway(FailedGateway(), metrics)
    context = ExecutionContext("actor", "org", "corr", "internal", "test")

    asyncio.run(gateway.call_tool("jira__search", {}, context))

    rendered = metrics.render_prometheus()
    assert 'tactiqo_tool_calls_total{server_family="jira",outcome="failure"} 1' in rendered
    assert "provider-secret-error" not in rendered
