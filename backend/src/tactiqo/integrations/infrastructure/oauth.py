"""OAuth 2.1 + PKCE support for tenant-managed MCP connections."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from tactiqo.integrations.domain.models import (
    ConnectionScope,
    ConnectionStatus,
    IntegrationConnection,
    IntegrationProvider,
    OAuthStart,
    ResolvedConnection,
)

if TYPE_CHECKING:
    from tactiqo.integrations.application.ports import (
        CredentialCipher,
        IntegrationConnectionRepository,
    )
    from tactiqo.integrations.application.service import IntegrationConnectionService
    from tactiqo.shared.domain.execution import ExecutionContext

_JIRA_METADATA = "https://mcp.atlassian.com/.well-known/oauth-authorization-server"
_SLACK_METADATA = "https://mcp.slack.com/.well-known/oauth-authorization-server"
_JIRA_ENDPOINT = "https://mcp.atlassian.com/v2/mcp?tools=all"
_SLACK_ENDPOINT = "https://mcp.slack.com/mcp"
_JIRA_SCOPES = "read:jira:agent-interface write:jira:agent-interface"
_SLACK_SCOPES = (
    "channels:history channels:read chat:write files:read groups:history groups:read "
    "im:history mpim:history search:read.files search:read.private search:read.public "
    "search:read.users users:read"
)


class OAuthFlowError(RuntimeError):
    """Safe OAuth failure that contains no provider secrets."""


@dataclass(frozen=True, slots=True)
class OAuthClient:
    """Provider client registration used for one authorization flow."""

    client_id: str
    client_secret: str | None
    authorization_endpoint: str
    token_endpoint: str
    scope: str


class OAuthFlowCoordinator:
    """Start and finish browser OAuth without exposing provider tokens."""

    def __init__(  # noqa: PLR0913
        self,
        connection_service: IntegrationConnectionService,
        encryption_key: str,
        public_api_base_url: str,
        web_base_url: str,
        slack_client_id: str | None,
        slack_client_secret: str | None,
        timeout_seconds: float,
    ) -> None:
        """Configure provider discovery, state protection, and browser return URLs."""
        self._connections = connection_service
        self._state = Fernet(encryption_key.encode())
        self._api_base = public_api_base_url.rstrip("/")
        self._web_base = web_base_url.rstrip("/")
        self._slack_client_id = slack_client_id
        self._slack_client_secret = slack_client_secret
        self._timeout = timeout_seconds

    async def start(
        self,
        provider: IntegrationProvider,
        name: str,
        scope: ConnectionScope,
        context: ExecutionContext,
    ) -> OAuthStart:
        """Create a signed, short-lived state and return the provider consent URL."""
        self._connections.require_manager(scope, context)
        callback = self._callback(provider)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        client = await self._client(provider, callback)
        state_payload = {
            "provider": provider.value,
            "name": name.strip(),
            "scope": scope.value,
            "organization_id": context.organization_id,
            "actor_id": context.actor_id,
            "verifier": verifier,
            "client_id": client.client_id,
            # Slack's long-lived platform secret never travels through the browser.
            # Jira DCR creates an ephemeral client secret that must survive callback.
            "client_secret": (
                client.client_secret if provider is IntegrationProvider.JIRA else None
            ),
            "token_endpoint": client.token_endpoint,
            "issued_at": datetime.now(UTC).isoformat(),
            "nonce": secrets.token_urlsafe(24),
        }
        state = self._state.encrypt(json.dumps(state_payload).encode()).decode()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client.client_id,
                "redirect_uri": callback,
                "scope": client.scope,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return OAuthStart(f"{client.authorization_endpoint}?{query}")

    async def callback(
        self,
        provider: IntegrationProvider,
        code: str,
        state: str,
        context: ExecutionContext,
    ) -> IntegrationConnection:
        """Validate callback context, exchange the code, and persist encrypted tokens."""
        payload = self._decode_state(state)
        if (
            payload.get("provider") != provider.value
            or payload.get("organization_id") != context.organization_id
            or payload.get("actor_id") != context.actor_id
        ):
            message = "OAuth state does not match the current tenant session."
            raise OAuthFlowError(message)
        token = await self._exchange(provider, payload, code)
        material = self._credential_material(provider, payload, token)
        endpoint = _JIRA_ENDPOINT if provider is IntegrationProvider.JIRA else _SLACK_ENDPOINT
        return await self._connections.create(
            provider=provider,
            name=str(payload["name"]),
            endpoint_url=endpoint,
            authorization=json.dumps(material, separators=(",", ":")),
            scope=ConnectionScope(str(payload["scope"])),
            context=context,
        )

    @property
    def success_url(self) -> str:
        """Return the frontend destination after a successful callback."""
        return f"{self._web_base}/?integration=connected"

    @property
    def error_url(self) -> str:
        """Return the frontend destination after a failed callback."""
        return f"{self._web_base}/?integration=error"

    async def _client(self, provider: IntegrationProvider, callback: str) -> OAuthClient:
        metadata_url = _JIRA_METADATA if provider is IntegrationProvider.JIRA else _SLACK_METADATA
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            metadata_response = await client.get(metadata_url)
            metadata_response.raise_for_status()
            metadata = metadata_response.json()
            if provider is IntegrationProvider.JIRA:
                registration = await client.post(
                    str(metadata["registration_endpoint"]),
                    json={
                        "client_name": "Tactiqo AI Operations Platform",
                        "redirect_uris": [callback],
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"],
                        "token_endpoint_auth_method": "client_secret_post",
                    },
                )
                registration.raise_for_status()
                registered = registration.json()
                client_id = str(registered["client_id"])
                client_secret = registered.get("client_secret")
            else:
                if not self._slack_client_id or not self._slack_client_secret:
                    message = "Slack OAuth app credentials are not configured."
                    raise OAuthFlowError(message)
                client_id = self._slack_client_id
                client_secret = self._slack_client_secret
        return OAuthClient(
            client_id,
            str(client_secret) if client_secret else None,
            str(metadata["authorization_endpoint"]),
            str(metadata["token_endpoint"]),
            _JIRA_SCOPES if provider is IntegrationProvider.JIRA else _SLACK_SCOPES,
        )

    async def _exchange(
        self, provider: IntegrationProvider, payload: dict[str, Any], code: str
    ) -> dict[str, Any]:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._callback(provider),
            "client_id": str(payload["client_id"]),
            "code_verifier": str(payload["verifier"]),
        }
        client_secret = (
            payload.get("client_secret")
            if provider is IntegrationProvider.JIRA
            else self._slack_client_secret
        )
        if client_secret:
            form["client_secret"] = str(client_secret)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(str(payload["token_endpoint"]), data=form)
            response.raise_for_status()
            token_value: object = response.json()
        if not isinstance(token_value, dict):
            message = "OAuth provider returned an invalid token response."
            raise OAuthFlowError(message)
        token: dict[str, Any] = token_value
        if token.get("ok") is False:
            message = "OAuth provider rejected the authorization code."
            raise OAuthFlowError(message)
        return token

    def _decode_state(self, state: str) -> dict[str, Any]:
        try:
            decoded = self._state.decrypt(state.encode(), ttl=600)
            value = json.loads(decoded)
        except (InvalidToken, json.JSONDecodeError) as error:
            message = "OAuth state is invalid or expired."
            raise OAuthFlowError(message) from error
        if not isinstance(value, dict):
            message = "OAuth state payload is invalid."
            raise OAuthFlowError(message)
        return value

    def _credential_material(
        self,
        provider: IntegrationProvider,
        payload: dict[str, Any],
        token: dict[str, Any],
    ) -> dict[str, Any]:
        nested_token = token.get("authed_user")
        user_token: dict[str, Any] = nested_token if isinstance(nested_token, dict) else token
        access_token = user_token.get("access_token")
        if not access_token:
            message = "OAuth provider response did not contain an access token."
            raise OAuthFlowError(message)
        expires_in = int(user_token.get("expires_in") or token.get("expires_in") or 3600)
        return {
            "kind": "oauth",
            "access_token": str(access_token),
            "refresh_token": user_token.get("refresh_token") or token.get("refresh_token"),
            "expires_at": (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat(),
            "token_endpoint": str(payload["token_endpoint"]),
            "client_id": str(payload["client_id"]),
            "client_secret": (
                payload.get("client_secret")
                if provider is IntegrationProvider.JIRA
                else self._slack_client_secret
            ),
        }

    def _callback(self, provider: IntegrationProvider) -> str:
        return f"{self._api_base}/api/v1/integrations/oauth/{provider.value}/callback"


class OAuthCredentialResolver:
    """Resolve manual or OAuth credentials and refresh expiring OAuth tokens."""

    def __init__(
        self,
        repository: IntegrationConnectionRepository,
        cipher: CredentialCipher,
        timeout_seconds: float,
    ) -> None:
        """Configure encrypted persistence and bounded provider refresh requests."""
        self._repository = repository
        self._cipher = cipher
        self._timeout = timeout_seconds

    async def authorization_for(
        self, resolved: ResolvedConnection, context: ExecutionContext
    ) -> str:
        """Return a usable header and rotate an expiring OAuth credential."""
        plaintext = self._cipher.decrypt(resolved.encrypted_authorization)
        try:
            material = json.loads(plaintext)
        except json.JSONDecodeError:
            return plaintext
        if not isinstance(material, dict) or material.get("kind") != "oauth":
            return plaintext
        expires_at = datetime.fromisoformat(str(material["expires_at"]))
        if expires_at > datetime.now(UTC) + timedelta(seconds=60):
            return f"Bearer {material['access_token']}"
        refresh_token = material.get("refresh_token")
        if not refresh_token:
            await self._repository.mark_status(
                resolved.connection.id, ConnectionStatus.EXPIRED, context
            )
            message = "OAuth access token expired and cannot be refreshed."
            raise OAuthFlowError(message)
        try:
            refreshed = await self._refresh(material, str(refresh_token))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            await self._repository.mark_status(
                resolved.connection.id, ConnectionStatus.ERROR, context
            )
            message = "OAuth credential refresh failed."
            raise OAuthFlowError(message) from error
        material.update(refreshed)
        encrypted = self._cipher.encrypt(json.dumps(material, separators=(",", ":")))
        updated = await self._repository.replace_credential(
            resolved.connection.id, encrypted, context
        )
        if not updated:
            message = "OAuth connection is no longer active."
            raise OAuthFlowError(message)
        return f"Bearer {material['access_token']}"

    async def _refresh(self, material: dict[str, Any], refresh_token: str) -> dict[str, Any]:
        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": str(material["client_id"]),
        }
        if material.get("client_secret"):
            form["client_secret"] = str(material["client_secret"])
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(str(material["token_endpoint"]), data=form)
            response.raise_for_status()
            token_value: object = response.json()
        if not isinstance(token_value, dict):
            message = "OAuth provider returned an invalid refresh response."
            raise OAuthFlowError(message)
        token: dict[str, Any] = token_value
        if token.get("ok") is False or not token.get("access_token"):
            message = "OAuth token refresh failed."
            raise OAuthFlowError(message)
        expires_in = int(token.get("expires_in") or 3600)
        return {
            "access_token": str(token["access_token"]),
            "refresh_token": token.get("refresh_token") or refresh_token,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat(),
        }
