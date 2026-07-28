"""Official MCP SDK adapter with policy-owned risk classification."""

import json
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.policy import ToolPolicy
from tactiqo.tools.domain.models import ToolDefinition, ToolResult


class McpToolGateway:
    """Connect to one remote MCP server without exposing SDK objects upstream."""

    def __init__(
        self,
        server_url: str,
        policy: ToolPolicy,
        timeout_seconds: float,
        max_result_characters: int,
        server_label: str = "tactiqo-demo",
    ) -> None:
        """Configure a bounded MCP Streamable HTTP connection."""
        self._server_url = server_url
        self._policy = policy
        self._timeout_seconds = timeout_seconds
        self._max_result_characters = max_result_characters
        self._server_label = server_label

    async def list_tools(self) -> list[ToolDefinition]:
        """Discover tools and normalize annotations to platform policy values."""
        async with (
            httpx.AsyncClient(timeout=self._timeout_seconds) as http_client,
            streamable_http_client(
                self._server_url,
                http_client=http_client,
            ) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            response = await session.list_tools()
        definitions: list[ToolDefinition] = []
        for tool in response.tools:
            annotations = tool.annotations
            read_only_hint = annotations.readOnlyHint if annotations is not None else None
            definitions.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=dict(tool.inputSchema),
                    risk=self._policy.classify(tool.name, read_only_hint=read_only_hint),
                    server_label=self._server_label,
                )
            )
        return definitions

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Execute a policy-approved MCP call with bounded untrusted output."""
        del context
        async with (
            httpx.AsyncClient(timeout=self._timeout_seconds) as http_client,
            streamable_http_client(
                self._server_url,
                http_client=http_client,
            ) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            response = await session.call_tool(name, arguments)
        parts: list[str] = []
        for item in response.content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
            else:
                parts.append(json.dumps(item.model_dump(mode="json"), ensure_ascii=False))
        content = "\n".join(parts)[: self._max_result_characters]
        return ToolResult(
            call_id="",
            name=name,
            content=content,
            is_error=bool(response.isError),
        )


class DisabledToolGateway:
    """Explicit no-tool adapter for degraded local operation and tests."""

    async def list_tools(self) -> list[ToolDefinition]:
        """Return no tools rather than pretending a server is available."""
        return []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Return an honest disabled result."""
        del arguments, context
        return ToolResult(
            call_id="",
            name=name,
            content="Tool execution is disabled in this environment.",
            is_error=True,
        )
