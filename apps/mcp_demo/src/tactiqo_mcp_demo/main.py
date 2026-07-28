"""Small MCP server proving discovery, read tools, and approved writes."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP(
    "Tactiqo Project Operations",
    host="0.0.0.0",  # noqa: S104 - container bind
    port=8100,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Get project snapshot",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def get_project_snapshot(project_code: str) -> str:
    """Return a local demonstration snapshot for a project code."""
    return json.dumps(
        {
            "project_code": project_code,
            "phase": "F1 — Agentic Knowledge Core",
            "health": "on_track",
            "progress_percent": 72,
            "next_gate": "functional flow verification",
            "source": "local MCP demonstration data",
        },
        ensure_ascii=False,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        title="List overdue items",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def list_overdue_items(project_code: str) -> str:
    """Return bounded local demonstration overdue work."""
    return json.dumps(
        {
            "project_code": project_code,
            "items": [
                {
                    "id": "F1-17",
                    "title": "Validate approval flow",
                    "owner": "Platform Engineering",
                    "days_overdue": 1,
                }
            ],
            "source": "local MCP demonstration data",
        },
        ensure_ascii=False,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        title="Create follow-up task",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
)
def create_follow_up_task(project_code: str, title: str, priority: str = "medium") -> str:
    """Create a local demonstration task after platform approval."""
    return json.dumps(
        {
            "created": True,
            "task_id": f"DEMO-{uuid4().hex[:8].upper()}",
            "project_code": project_code,
            "title": title,
            "priority": priority,
            "created_at": datetime.now(UTC).isoformat(),
            "source": "local MCP demonstration store",
        },
        ensure_ascii=False,
    )


def main() -> None:
    """Serve the Streamable HTTP MCP transport."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
