"""OIDC verification security tests."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from tactiqo.identity.infrastructure.oidc import IdentityTokenError, OidcIdentityProvider


class StaticJwks:
    """Return test-owned public keys without network access."""

    def __init__(self, document: dict[str, Any]) -> None:
        """Store one deterministic JWKS document."""
        self._document = document

    async def load(self) -> dict[str, Any]:
        """Return the configured JWKS document."""
        return self._document


def _fixture() -> tuple[OidcIdentityProvider, rsa.RSAPrivateKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    provider = OidcIdentityProvider(
        "https://id.example", "tactiqo", StaticJwks({"keys": [public_jwk]})
    )
    return provider, private_key


def _token(private_key: rsa.RSAPrivateKey, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": "https://id.example",
        "aud": "tactiqo",
        "sub": "immutable-subject",
        "nonce": "expected-nonce",
        "jti": "unique-token",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "amr": ["pwd", "mfa"],
    }
    claims.update(overrides)
    return jwt.encode(
        claims, private_key, algorithm="RS256", headers={"kid": "test-key", "typ": "JWT"}
    )


@pytest.mark.anyio
async def test_valid_token_maps_minimum_verified_claims() -> None:
    """A valid token returns immutable subject and MFA assurance."""
    provider, private_key = _fixture()
    verified = await provider.verify_id_token(_token(private_key), "expected-nonce")
    assert verified.subject == "immutable-subject"
    assert verified.assurance.value == "mfa"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://attacker.example"},
        {"aud": "another-app"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"nonce": "replayed-nonce"},
    ],
)
async def test_invalid_security_claims_fail_closed(overrides: dict[str, object]) -> None:
    """Issuer, audience, expiry, and nonce mismatches never authenticate."""
    provider, private_key = _fixture()
    with pytest.raises(IdentityTokenError):
        await provider.verify_id_token(_token(private_key, **overrides), "expected-nonce")
