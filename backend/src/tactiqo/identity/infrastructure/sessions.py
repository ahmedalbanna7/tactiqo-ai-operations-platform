"""Opaque session persistence and OIDC callback orchestration."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from tactiqo.identity.infrastructure.tables import (
    AuthAuditRow,
    AuthSessionRow,
    DepartmentMemberRow,
    DepartmentRow,
    InvitationRow,
    OrganizationMemberRow,
    RoleAssignmentRow,
    UserRow,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tactiqo.identity.domain.models import VerifiedIdentityToken
    from tactiqo.identity.infrastructure.oidc import OidcIdentityProvider


class SessionError(ValueError):
    """Safe authentication/session failure."""


@dataclass(frozen=True, slots=True)
class SessionIssue:
    """One newly issued opaque session returned only as a secure cookie."""

    token: str
    session_id: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class SessionView:
    """Secret-free session metadata."""

    id: UUID
    assurance: str
    created_at: datetime
    expires_at: datetime
    current: bool


class SqlSessionService:
    """Map immutable OIDC subjects and manage revocable opaque sessions."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], ttl_seconds: int) -> None:
        """Configure persistence and bounded session lifetime."""
        self._sessions = sessions
        self._ttl = ttl_seconds

    async def issue(  # noqa: PLR0913 - explicit security context fields
        self,
        verified: VerifiedIdentityToken,
        organization_id: str,
        display_name: str,
        email: str | None,
        user_agent: str,
        correlation_id: str,
        invitation_token: str | None = None,
    ) -> SessionIssue:
        """Issue once per provider token after active membership validation."""
        opaque = secrets.token_urlsafe(48)
        now = datetime.now(UTC)
        expires = min(verified.expires_at, now + timedelta(seconds=self._ttl))
        async with self._sessions() as session, session.begin():
            user = await session.scalar(
                select(UserRow).where(
                    UserRow.provider == verified.issuer,
                    UserRow.subject == verified.subject,
                )
            )
            if user is None:
                user = UserRow(
                    provider=verified.issuer,
                    subject=verified.subject,
                    display_name=display_name,
                    email=email,
                )
                session.add(user)
                await session.flush()
            member = await session.get(OrganizationMemberRow, (organization_id, user.id))
            if invitation_token:
                invitation_hash = hashlib.sha256(invitation_token.encode()).hexdigest()
                invitation = await session.scalar(
                    select(InvitationRow)
                    .where(
                        InvitationRow.token_hash == invitation_hash,
                        InvitationRow.organization_id == organization_id,
                        InvitationRow.status == "pending",
                        InvitationRow.expires_at > now,
                    )
                    .with_for_update()
                )
                department = None
                if invitation is not None and invitation.department_id is not None:
                    department = await session.scalar(
                        select(DepartmentRow).where(
                            DepartmentRow.id == invitation.department_id,
                            DepartmentRow.organization_id == organization_id,
                            DepartmentRow.status == "active",
                        )
                    )
                if invitation is None or department is None:
                    raise SessionError
                is_new_member = member is None
                if member is None:
                    member = OrganizationMemberRow(
                        organization_id=organization_id,
                        user_id=user.id,
                        status="active",
                        classification_clearance="internal",
                    )
                    session.add(member)
                    session.add(
                        DepartmentMemberRow(
                            organization_id=organization_id,
                            department_id=department.id,
                            user_id=user.id,
                        )
                    )
                    session.add(
                        RoleAssignmentRow(
                            organization_id=organization_id,
                            user_id=user.id,
                            role_code="employee",
                            assigned_by=invitation.invited_by,
                        )
                    )
                elif member.status != "active" or member.revoked_at is not None:
                    raise SessionError
                if not is_new_member and await session.get(
                    DepartmentMemberRow, (organization_id, department.id, user.id)
                ) is None:
                    session.add(
                        DepartmentMemberRow(
                            organization_id=organization_id,
                            department_id=department.id,
                            user_id=user.id,
                        )
                    )
                invitation.status = "accepted"
                invitation.accepted_at = now
                session.add(
                    AuthAuditRow(
                        event_type="organization.invitation.accepted",
                        user_id=user.id,
                        organization_id=organization_id,
                        correlation_id=str(invitation.id),
                        safe_detail=f"department={department.id}",
                    )
                )
            if member is None or member.status != "active" or member.revoked_at is not None:
                raise SessionError
            row = AuthSessionRow(
                user_id=user.id,
                organization_id=organization_id,
                token_hash=hashlib.sha256(opaque.encode()).hexdigest(),
                provider_token_id_hash=hashlib.sha256(verified.token_id.encode()).hexdigest(),
                assurance=verified.assurance.value,
                user_agent_hash=hashlib.sha256(user_agent.encode()).hexdigest(),
                expires_at=expires,
            )
            session.add(row)
            try:
                await session.flush()
            except IntegrityError as exc:
                raise SessionError from exc
            session.add(
                AuthAuditRow(
                    event_type="session.issued",
                    user_id=user.id,
                    organization_id=organization_id,
                    session_id=row.id,
                    correlation_id=correlation_id,
                )
            )
            return SessionIssue(opaque, row.id, expires)

    async def list(
        self, user_id: UUID, organization_id: str, current_id: UUID
    ) -> list[SessionView]:
        """List only the caller's tenant sessions without hashes or claims."""
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(AuthSessionRow).where(
                        AuthSessionRow.user_id == user_id,
                        AuthSessionRow.organization_id == organization_id,
                        AuthSessionRow.revoked_at.is_(None),
                    )
                )
            ).all()
            return [
                SessionView(
                    row.id, row.assurance, row.created_at, row.expires_at, row.id == current_id
                )
                for row in rows
            ]

    async def revoke(
        self, user_id: UUID, organization_id: str, session_id: UUID, correlation_id: str
    ) -> bool:
        """Revoke one caller-owned session using all tenant predicates."""
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(AuthSessionRow)
                .where(
                    AuthSessionRow.id == session_id,
                    AuthSessionRow.user_id == user_id,
                    AuthSessionRow.organization_id == organization_id,
                    AuthSessionRow.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                return False
            session.add(
                AuthAuditRow(
                    event_type="session.revoked",
                    user_id=user_id,
                    organization_id=organization_id,
                    session_id=session_id,
                    correlation_id=correlation_id,
                )
            )
            return True

    async def refresh(
        self,
        user_id: UUID,
        organization_id: str,
        session_id: UUID,
        correlation_id: str,
    ) -> SessionIssue | None:
        """Rotate an active session token while preserving its identity."""
        opaque = secrets.token_urlsafe(48)
        expires = datetime.now(UTC) + timedelta(seconds=self._ttl)
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(AuthSessionRow)
                .where(
                    AuthSessionRow.id == session_id,
                    AuthSessionRow.user_id == user_id,
                    AuthSessionRow.organization_id == organization_id,
                    AuthSessionRow.revoked_at.is_(None),
                    AuthSessionRow.expires_at > datetime.now(UTC),
                )
                .values(
                    token_hash=hashlib.sha256(opaque.encode()).hexdigest(),
                    expires_at=expires,
                )
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                return None
            session.add(
                AuthAuditRow(
                    event_type="session.refreshed",
                    user_id=user_id,
                    organization_id=organization_id,
                    session_id=session_id,
                    correlation_id=correlation_id,
                )
            )
            return SessionIssue(opaque, session_id, expires)


class OidcLoginCoordinator:
    """Create PKCE login state and exchange callbacks without exposing tokens."""

    def __init__(  # noqa: PLR0913 - explicit immutable OIDC client configuration
        self,
        authorization_endpoint: str,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        state_key: str,
        provider: OidcIdentityProvider,
        sessions: SqlSessionService,
    ) -> None:
        """Configure trusted provider endpoints and state protection."""
        self._authorization_endpoint = authorization_endpoint
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._cipher = Fernet(state_key.encode())
        self._provider = provider
        self._sessions = sessions

    def start(self, organization_id: str, invitation_token: str | None = None) -> str:
        """Return provider URL containing signed tenant, nonce, and PKCE state."""
        nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        payload = {
            "organization_id": organization_id,
            "nonce": nonce,
            "verifier": verifier,
            "exp": int(datetime.now(UTC).timestamp()) + 600,
        }
        if invitation_token:
            payload["invitation_token"] = invitation_token
        state = self._cipher.encrypt(json.dumps(payload).encode()).decode()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": "openid profile email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self._authorization_endpoint}?{query}"

    async def callback(
        self, code: str, state: str, user_agent: str, correlation_id: str
    ) -> SessionIssue:
        """Exchange code, verify ID token, and issue an opaque application session."""
        try:
            payload = json.loads(self._cipher.decrypt(state.encode(), ttl=600))
        except (InvalidToken, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise SessionError from exc
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(
                self._token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code_verifier": payload["verifier"],
                },
            )
            response.raise_for_status()
            body = response.json()
        verified = await self._provider.verify_id_token(
            str(body["id_token"]), str(payload["nonce"])
        )
        return await self._sessions.issue(
            verified,
            str(payload["organization_id"]),
            str(body.get("name", verified.subject)),
            body.get("email"),
            user_agent,
            correlation_id,
            payload.get("invitation_token"),
        )
