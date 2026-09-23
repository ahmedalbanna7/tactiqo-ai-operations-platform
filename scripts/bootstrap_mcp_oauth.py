"""Bootstrap OAuth 2.1 for an MCP server using PKCE and local token storage."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import httpx
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from pydantic import AnyUrl


class JsonTokenStorage(TokenStorage):
    """Persist OAuth state in a git-ignored, user-local JSON file."""

    def __init__(self, path: Path) -> None:
        """Bind storage to one provider-specific, git-ignored file."""
        self._path = path

    def _read(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        return cast("dict[str, object]", json.loads(self._path.read_text(encoding="utf-8")))

    def _write(self, data: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def get_tokens(self) -> OAuthToken | None:
        """Load a previously issued token set."""
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """Persist an issued or refreshed token set."""
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Load dynamic client-registration metadata."""
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """Persist dynamic client-registration metadata."""
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._write(data)


class LoopbackCallback:
    """Receive one OAuth callback on a loopback-only HTTP socket."""

    def __init__(self, host: str, port: int) -> None:
        """Bind a callback receiver to an explicit loopback address."""
        self._host = host
        self._port = port

    async def receive(self) -> tuple[str, str | None]:
        """Wait for one callback and return its code and CSRF state."""
        loop = asyncio.get_running_loop()
        result: asyncio.Future[tuple[str, str | None]] = loop.create_future()

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            request_line = (await reader.readline()).decode("ascii", errors="replace")
            target = request_line.split(" ", 2)[1]
            params = parse_qs(urlsplit(target).query)
            code = params.get("code", [""])[0]
            state = params.get("state", [None])[0]
            body = b"Tactiqo authorization received. You may close this tab."
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            if not result.done():
                result.set_result((code, state))

        server = await asyncio.start_server(handle, self._host, self._port)
        print(f"CALLBACK_READY=http://{self._host}:{self._port}/callback", flush=True)
        async with server:
            return await result


async def bootstrap(server_url: str, provider: str, port: int) -> None:
    """Authorize one MCP provider and verify tool discovery."""
    callback = LoopbackCallback("127.0.0.1", port)
    storage = JsonTokenStorage(Path(".local") / "oauth" / f"{provider}.json")

    async def show_redirect(url: str) -> None:
        print(f"AUTHORIZATION_URL={url}", flush=True)

    auth = OAuthClientProvider(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            client_name="Tactiqo AI Operations Platform",
            redirect_uris=[AnyUrl(f"http://127.0.0.1:{port}/callback")],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        ),
        storage=storage,
        redirect_handler=show_redirect,
        callback_handler=callback.receive,
    )
    async with (
        httpx.AsyncClient(auth=auth, timeout=300, follow_redirects=True) as client,
        streamable_http_client(server_url, http_client=client) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
    print(f"CONNECTED_PROVIDER={provider}", flush=True)
    print(f"DISCOVERED_TOOL_COUNT={len(tools.tools)}", flush=True)


def main() -> None:
    """Parse safe public configuration and run the OAuth bootstrap."""
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=("jira", "slack"))
    parser.add_argument("server_url")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(bootstrap(args.server_url, args.provider, args.port))


if __name__ == "__main__":
    main()
