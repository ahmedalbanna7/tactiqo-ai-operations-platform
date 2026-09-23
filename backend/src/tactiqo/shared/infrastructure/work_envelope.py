"""Signed minimum execution context for internal durable work."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from tactiqo.shared.domain.execution import ExecutionContext

MIN_SIGNING_KEY_CHARACTERS = 32


class InvalidWorkEnvelopeError(ValueError):
    """Raised when internal work context is expired or tampered with."""


class WorkEnvelopeSigner:
    """Serialize and authenticate minimum context without user/provider tokens."""

    def __init__(self, key: str, ttl_seconds: int = 900) -> None:
        """Configure an independent signing key and bounded lifetime."""
        if len(key) < MIN_SIGNING_KEY_CHARACTERS:
            message = "Work-envelope signing key must contain at least 32 characters."
            raise ValueError(message)
        self._key = key.encode()
        self._ttl = ttl_seconds

    def sign(self, context: ExecutionContext) -> str:
        """Sign only authorization inputs required by an internal worker."""
        payload: dict[str, Any] = {
            "v": 1,
            "exp": int(time.time()) + self._ttl,
            "actor_id": context.actor_id,
            "organization_id": context.organization_id,
            "correlation_id": context.correlation_id,
            "classification_clearance": context.classification_clearance,
            "policy_version": context.policy_version,
            "department_ids": list(context.department_ids),
            "team_ids": list(context.team_ids),
            "project_ids": list(context.project_ids),
            "role_codes": list(context.role_codes),
            "data_region": context.data_region,
            "session_assurance": context.session_assurance,
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(self._key, body, hashlib.sha256).digest()
        encoded_body = base64.urlsafe_b64encode(body).decode()
        encoded_signature = base64.urlsafe_b64encode(signature).decode()
        return f"{encoded_body}.{encoded_signature}"

    def verify(self, envelope: str) -> ExecutionContext:
        """Verify signature and expiry before reconstructing minimum context."""
        try:
            body_part, signature_part = envelope.split(".", maxsplit=1)
            body = base64.urlsafe_b64decode(body_part)
            signature = base64.urlsafe_b64decode(signature_part)
            expected = hmac.new(self._key, body, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise InvalidWorkEnvelopeError
            payload = json.loads(body)
            if payload.get("v") != 1 or int(payload["exp"]) < int(time.time()):
                raise InvalidWorkEnvelopeError
            return ExecutionContext(
                actor_id=str(payload["actor_id"]),
                organization_id=str(payload["organization_id"]),
                correlation_id=str(payload["correlation_id"]),
                classification_clearance=str(payload["classification_clearance"]),
                policy_version=str(payload["policy_version"]),
                organizational_unit_ids=tuple(payload.get("department_ids", [])),
                department_ids=tuple(payload.get("department_ids", [])),
                team_ids=tuple(payload.get("team_ids", [])),
                project_ids=tuple(payload.get("project_ids", [])),
                role_codes=tuple(payload.get("role_codes", [])),
                data_region=str(payload.get("data_region", "global")),
                session_assurance=str(payload.get("session_assurance", "standard")),
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            message = "Invalid internal work envelope."
            raise InvalidWorkEnvelopeError(message) from exc
