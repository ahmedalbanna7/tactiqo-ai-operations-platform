"""Security tests for signed internal work envelopes."""

import base64
import json

import pytest

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.work_envelope import (
    InvalidWorkEnvelopeError,
    WorkEnvelopeSigner,
)


def _context() -> ExecutionContext:
    return ExecutionContext(
        actor_id="user-1",
        organization_id="org-1",
        correlation_id="correlation-1",
        classification_clearance="confidential",
        policy_version="policy-7",
        organizational_unit_ids=("department-1",),
        department_ids=("department-1",),
        team_ids=("team-1",),
        project_ids=("project-1",),
        role_codes=("employee",),
        data_region="eg",
        session_id="secret-session-id",
        session_assurance="mfa",
    )


def test_round_trip_preserves_minimum_authorization_context() -> None:
    """A valid envelope restores every delegated authorization scope."""
    signer = WorkEnvelopeSigner("a" * 32)

    restored = signer.verify(signer.sign(_context()))

    assert restored.actor_id == "user-1"
    assert restored.organization_id == "org-1"
    assert restored.department_ids == ("department-1",)
    assert restored.team_ids == ("team-1",)
    assert restored.project_ids == ("project-1",)
    assert restored.role_codes == ("employee",)
    assert restored.session_assurance == "mfa"


def test_envelope_never_contains_session_or_provider_tokens() -> None:
    """Durable work cannot leak reusable authentication secrets."""
    signer = WorkEnvelopeSigner("a" * 32)
    encoded_body = signer.sign(_context()).split(".", maxsplit=1)[0]
    payload = json.loads(base64.urlsafe_b64decode(encoded_body))

    assert "session_id" not in payload
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_tampered_envelope_is_rejected() -> None:
    """Changing a signed body invalidates the envelope."""
    signer = WorkEnvelopeSigner("a" * 32)
    envelope = signer.sign(_context())
    body, signature = envelope.split(".", maxsplit=1)
    tampered_body = ("A" if body[0] != "A" else "B") + body[1:]

    with pytest.raises(InvalidWorkEnvelopeError):
        signer.verify(f"{tampered_body}.{signature}")


def test_expired_envelope_is_rejected() -> None:
    """Workers reject stale authorization context."""
    signer = WorkEnvelopeSigner("a" * 32, ttl_seconds=-1)

    with pytest.raises(InvalidWorkEnvelopeError):
        signer.verify(signer.sign(_context()))


def test_short_signing_key_is_rejected() -> None:
    """Weak signing keys fail during composition."""
    with pytest.raises(ValueError, match="at least 32"):
        WorkEnvelopeSigner("short")
