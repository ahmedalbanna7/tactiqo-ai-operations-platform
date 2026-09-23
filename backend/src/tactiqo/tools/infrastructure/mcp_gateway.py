"""Official MCP SDK adapter with policy-owned risk classification."""

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.policy import ToolPolicy
from tactiqo.tools.application.ports import ToolGateway
from tactiqo.tools.domain.models import ToolDefinition, ToolResult


class McpToolGateway:
    """Connect to one remote MCP server without exposing SDK objects upstream."""

    def __init__(  # noqa: PLR0913 - explicit network safety configuration
        self,
        server_url: str,
        policy: ToolPolicy,
        timeout_seconds: float,
        max_result_characters: int,
        server_label: str = "tactiqo-demo",
        headers: Mapping[str, str] | None = None,
        auth: httpx.Auth | None = None,
    ) -> None:
        """Configure a bounded MCP Streamable HTTP connection."""
        self._server_url = server_url
        self._policy = policy
        self._timeout_seconds = timeout_seconds
        self._max_result_characters = max_result_characters
        self._server_label = server_label
        self._headers = dict(headers or {})
        self._auth = auth

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Discover tools and normalize annotations to platform policy values."""
        del context
        remote_tools: list[Any] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        async with (
            httpx.AsyncClient(
                timeout=self._timeout_seconds,
                headers=self._headers,
                auth=self._auth,
            ) as http_client,
            streamable_http_client(
                self._server_url,
                http_client=http_client,
            ) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            for _ in range(20):
                response = await session.list_tools(cursor=cursor)
                remote_tools.extend(response.tools)
                cursor = response.nextCursor
                if cursor is None:
                    break
                if cursor in seen_cursors:
                    msg = "MCP server returned a repeated pagination cursor."
                    raise RuntimeError(msg)
                seen_cursors.add(cursor)
            else:
                msg = "MCP tool discovery exceeded the 20-page safety limit."
                raise RuntimeError(msg)
        definitions: list[ToolDefinition] = []
        for tool in remote_tools:
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
            httpx.AsyncClient(
                timeout=self._timeout_seconds,
                headers=self._headers,
                auth=self._auth,
            ) as http_client,
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


class CompositeMcpToolGateway:
    """Expose several MCP servers through collision-safe qualified tool names."""

    _separator = "__"

    def __init__(self, gateways: Mapping[str, ToolGateway]) -> None:
        """Register gateways by stable, separator-free labels."""
        if any(self._separator in label for label in gateways):
            message = "MCP server labels cannot contain '__'."
            raise ValueError(message)
        self._gateways = dict(gateways)

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Discover all servers concurrently and qualify every tool name."""
        labels = list(self._gateways)
        discovered = await asyncio.gather(
            *(self._gateways[label].list_tools(context) for label in labels)
        )
        return [
            ToolDefinition(
                name=f"{label}{self._separator}{tool.name}",
                description=tool.description,
                input_schema=tool.input_schema,
                risk=tool.risk,
                server_label=label,
            )
            for label, tools in zip(labels, discovered, strict=True)
            for tool in tools
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Route one qualified name to its owning MCP server."""
        label, separator, remote_name = name.partition(self._separator)
        gateway = self._gateways.get(label)
        if not separator or not remote_name or gateway is None:
            return ToolResult(
                call_id="",
                name=name,
                content="Unknown or unqualified MCP tool name.",
                is_error=True,
            )
        result = await gateway.call_tool(remote_name, arguments, context)
        return ToolResult(
            call_id=result.call_id,
            name=name,
            content=result.content,
            is_error=result.is_error,
        )


class DisabledToolGateway:
    """Explicit no-tool adapter for degraded local operation and tests."""

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Return no tools rather than pretending a server is available."""
        del context
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
