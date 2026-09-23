"""Unit tests for collision-safe multi-server MCP routing."""

import asyncio
from typing import Any

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ToolDefinition, ToolResult, ToolRisk
from tactiqo.tools.infrastructure.mcp_gateway import CompositeMcpToolGateway


class FakeGateway:
    """Minimal gateway test double."""

    def __init__(self, tool_name: str) -> None:
        """Store the one tool exposed by this test double."""
        self.tool_name = tool_name
        self.called_name: str | None = None

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Return the configured test tool."""
        del context
        return [
            ToolDefinition(
                name=self.tool_name,
                description="test",
                input_schema={"type": "object"},
                risk=ToolRisk.READ_ONLY,
                server_label="remote",
            )
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Record and return the routed remote name."""
        del arguments, context
        self.called_name = name
        return ToolResult(call_id="", name=name, content="ok", is_error=False)


def test_composite_gateway_qualifies_colliding_names() -> None:
    """Identical remote names remain distinct in the agent catalogue."""
    jira = FakeGateway("search")
    slack = FakeGateway("search")
    gateway = CompositeMcpToolGateway({"jira": jira, "slack": slack})

    context = ExecutionContext("actor", "org", "corr", "internal", "test")
    tools = asyncio.run(gateway.list_tools(context))

    assert [tool.name for tool in tools] == ["jira__search", "slack__search"]
    assert [tool.server_label for tool in tools] == ["jira", "slack"]


def test_composite_gateway_routes_qualified_call() -> None:
    """A qualified tool call reaches only its owning server."""
    jira = FakeGateway("get_issue")
    gateway = CompositeMcpToolGateway({"jira": jira})

    result = asyncio.run(
        gateway.call_tool(
            "jira__get_issue",
            {"key": "OPS-1"},
            None,  # type: ignore[arg-type]
        )
    )

    assert jira.called_name == "get_issue"
    assert result.name == "jira__get_issue"
    assert result.is_error is False


def test_composite_gateway_rejects_unqualified_call() -> None:
    """Unqualified names fail closed instead of guessing a server."""
    gateway = CompositeMcpToolGateway({"jira": FakeGateway("get_issue")})

    result = asyncio.run(
        gateway.call_tool("get_issue", {}, None)  # type: ignore[arg-type]
    )

    assert result.is_error is True
    assert result.name == "get_issue"
