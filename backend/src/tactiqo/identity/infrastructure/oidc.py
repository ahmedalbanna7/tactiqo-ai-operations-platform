"""Fail-closed generic OIDC ID-token verification."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
import jwt
from jwt import PyJWKSet

from tactiqo.identity.domain.models import SessionAssurance, VerifiedIdentityToken

MAX_JWKS_BYTES = 256_000


class IdentityTokenError(ValueError):
    """Publicly safe identity-token rejection."""


class JwksProvider(Protocol):
    """Load public verification keys from a trusted issuer configuration."""

    async def load(self) -> dict[str, Any]:
        """Return one JWKS document."""


class RemoteJwksProvider:
    """Bounded HTTPS JWKS loader for a configured OIDC issuer."""

    def __init__(self, uri: str, timeout_seconds: float = 5.0) -> None:
        """Configure a trusted HTTPS JWKS endpoint and timeout."""
        if not uri.startswith("https://"):
            message = "OIDC JWKS URI must use HTTPS."
            raise ValueError(message)
        self._uri = uri
        self._timeout = timeout_seconds

    async def load(self) -> dict[str, Any]:
        """Fetch keys with redirects disabled and a strict response limit."""
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            response = await client.get(self._uri, headers={"Accept": "application/json"})
            response.raise_for_status()
            if len(response.content) > MAX_JWKS_BYTES:
                message = "OIDC JWKS response exceeds the configured limit."
                raise IdentityTokenError(message)
            document: dict[str, Any] = response.json()
            return document


class OidcIdentityProvider:
    """Verify asymmetric OIDC ID tokens against issuer-owned keys."""

    def __init__(self, issuer: str, audience: str, jwks: JwksProvider) -> None:
        """Configure exact issuer/audience and a replaceable key source."""
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks = jwks

    async def verify_id_token(self, token: str, expected_nonce: str) -> VerifiedIdentityToken:
        """Validate algorithm, key, issuer, audience, time, nonce, and token type."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            message = "OIDC ID token validation failed."
            raise IdentityTokenError(message) from exc
        if header.get("alg") not in {"RS256", "RS384", "RS512", "ES256", "ES384"}:
            message = "Unsupported OIDC signing algorithm."
            raise IdentityTokenError(message)
        if header.get("typ", "JWT") != "JWT":
            message = "Unexpected OIDC token type."
            raise IdentityTokenError(message)
        kid = header.get("kid")
        try:
            keys = PyJWKSet.from_dict(await self._jwks.load()).keys
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            message = "OIDC ID token validation failed."
            raise IdentityTokenError(message) from exc
        matching = [key for key in keys if key.key_id == kid]
        if len(matching) != 1:
            message = "OIDC signing key was not found."
            raise IdentityTokenError(message)
        try:
            claims = jwt.decode(
                token,
                matching[0].key,
                algorithms=[str(header["alg"])],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce", "jti"]},
            )
            audience = claims["aud"]
            audience_value = audience if isinstance(audience, str) else self._audience
            methods = claims.get("amr", [])
            assurance = (
                SessionAssurance.MFA
                if isinstance(methods, list) and "mfa" in methods
                else SessionAssurance.STANDARD
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            message = "OIDC ID token validation failed."
            raise IdentityTokenError(message) from exc
        if not hmac.compare_digest(str(claims["nonce"]), expected_nonce):
            message = "OIDC nonce mismatch."
            raise IdentityTokenError(message)
        return VerifiedIdentityToken(
            issuer=str(claims["iss"]),
            subject=str(claims["sub"]),
            audience=audience_value,
            nonce=str(claims["nonce"]),
            token_id=str(claims["jti"]),
            expires_at=datetime.fromtimestamp(int(claims["exp"]), UTC),
            authenticated_at=datetime.fromtimestamp(int(claims["iat"]), UTC),
            assurance=assurance,
        )
