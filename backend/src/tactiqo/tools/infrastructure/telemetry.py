"""Telemetry decorator for MCP tool gateways."""

from time import monotonic
from typing import Any

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.ports import ToolGateway
from tactiqo.tools.application.telemetry import ToolCallMetrics
from tactiqo.tools.domain.models import ToolDefinition, ToolResult

_SERVER_ALIASES = {
    "jira": "jira",
    "slack": "slack",
    "confluence": "confluence",
    "demo": "demo",
    "tactiqo-demo": "demo",
}


class InstrumentedToolGateway:
    """Measure actual gateway calls without exposing tool names or payloads."""

    def __init__(self, gateway: ToolGateway, metrics: ToolCallMetrics) -> None:
        """Wrap an existing gateway without changing its authorization contract."""
        self._gateway = gateway
        self._metrics = metrics

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Pass discovery through without emitting call metrics."""
        return await self._gateway.list_tools(context)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Measure call duration/outcome while preserving result and exception behavior."""
        started = monotonic()
        outcome = "failure"
        try:
            result = await self._gateway.call_tool(name, arguments, context)
            outcome = "failure" if result.is_error else "success"
            return result
        finally:
            self._metrics.observe(
                self._server_family(name),
                outcome,
                (monotonic() - started) * 1000,
            )

    @staticmethod
    def _server_family(qualified_name: str) -> str:
        """Map static or connection-qualified names to a fixed provider family."""
        prefix = qualified_name.partition("__")[0]
        if prefix == "tactiqo-demo":
            return "demo"
        provider = prefix.split("_", maxsplit=1)[0]
        return _SERVER_ALIASES.get(provider, "other")
