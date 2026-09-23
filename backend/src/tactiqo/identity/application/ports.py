"""Replaceable ports for authentication and scoped identity persistence."""

from typing import Protocol

from tactiqo.identity.domain.models import VerifiedIdentityToken


class IdentityProviderPort(Protocol):
    """Validate provider tokens without leaking vendor concerns into domain code."""

    async def verify_id_token(self, token: str, expected_nonce: str) -> VerifiedIdentityToken:
        """Verify signature and mandatory OIDC claims, or fail closed."""
