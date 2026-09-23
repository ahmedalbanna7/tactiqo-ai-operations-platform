"""Local OAuth token storage for remote MCP clients."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

if TYPE_CHECKING:
    from pathlib import Path


class JsonOAuthTokenStorage(TokenStorage):
    """Persist OAuth tokens and DCR metadata in a git-ignored runtime file."""

    def __init__(self, path: Path) -> None:
        """Bind storage to one provider-specific file."""
        self._path = path

    def _read(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        return cast("dict[str, object]", json.loads(self._path.read_text(encoding="utf-8")))

    def _write(self, data: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    async def get_tokens(self) -> OAuthToken | None:
        """Load the current token set, if authorized."""
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """Atomically persist an issued or refreshed token set."""
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Load dynamic client registration metadata."""
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """Atomically persist dynamic client registration metadata."""
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._write(data)
