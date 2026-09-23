"""Tenant-safe persistence for AI provider profiles."""

import builtins
import json
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.ai.domain.models import ProviderKind, ProviderProfile, ProviderStatus
from tactiqo.ai.infrastructure.tables import AIProviderProfileRow, AIProviderUsageRow
from tactiqo.identity.infrastructure.tables import AuthAuditRow, OrganizationRow


class SqlAIProfileRepository:
    """Persist active profiles and safe usage records in PostgreSQL."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the transaction factory."""
        self._sessions = sessions

    async def active(self, organization_id: str, kind: ProviderKind) -> ProviderProfile | None:
        """Return one exact-tenant enabled profile."""
        async with self._sessions() as session:
            row = await session.scalar(
                select(AIProviderProfileRow).where(
                    AIProviderProfileRow.organization_id == organization_id,
                    AIProviderProfileRow.kind == kind.value,
                    AIProviderProfileRow.status == ProviderStatus.ENABLED.value,
                )
            )
            return self._model(row) if row else None

    async def list(self, organization_id: str) -> list[ProviderProfile]:
        """List exact-tenant non-secret profiles."""
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(AIProviderProfileRow)
                    .where(AIProviderProfileRow.organization_id == organization_id)
                    .order_by(AIProviderProfileRow.kind, AIProviderProfileRow.name)
                )
            ).all()
            return [self._model(row) for row in rows]

    async def enabled(
        self, organization_id: str, kind: ProviderKind
    ) -> builtins.list[ProviderProfile]:
        """Return every enabled tenant profile ordered by explicit priority."""
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(AIProviderProfileRow)
                    .where(
                        AIProviderProfileRow.organization_id == organization_id,
                        AIProviderProfileRow.kind == kind.value,
                        AIProviderProfileRow.status == ProviderStatus.ENABLED.value,
                    )
                    .order_by(AIProviderProfileRow.routing_priority, AIProviderProfileRow.name)
                )
            ).all()
            return [self._model(row) for row in rows]

    async def upsert(self, organization_id: str, profile: ProviderProfile, actor_id: str) -> None:
        """Activate one validated profile without disabling other routed providers."""
        async with self._sessions() as session, session.begin():
            if profile.kind is ProviderKind.EMBEDDING:
                await session.execute(
                    update(AIProviderProfileRow)
                    .where(
                        AIProviderProfileRow.organization_id == organization_id,
                        AIProviderProfileRow.kind == ProviderKind.EMBEDDING.value,
                    )
                    .values(status=ProviderStatus.DISABLED.value)
                )
            row = await session.scalar(
                select(AIProviderProfileRow).where(
                    AIProviderProfileRow.organization_id == organization_id,
                    AIProviderProfileRow.name == profile.name,
                )
            )
            values = self._values(profile)
            if row is None:
                session.add(AIProviderProfileRow(organization_id=organization_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                row.version += 1
            await session.execute(
                update(OrganizationRow)
                .where(OrganizationRow.id == organization_id)
                .values(policy_version=str(uuid4()))
            )
            session.add(
                AuthAuditRow(
                    event_type="ai.profile.activated",
                    user_id=UUID(actor_id),
                    organization_id=organization_id,
                    correlation_id=profile.name,
                    safe_detail=(
                        f"kind={profile.kind.value};provider={profile.provider};"
                        f"model={profile.model};secret_reference_present={bool(profile.secret_reference)}"
                    ),
                )
            )

    async def disable(self, organization_id: str, name: str, actor_id: str) -> bool:
        """Disable an exact tenant-owned profile and invalidate routing policy."""
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(AIProviderProfileRow).where(
                    AIProviderProfileRow.organization_id == organization_id,
                    AIProviderProfileRow.name == name,
                )
            )
            if row is None:
                return False
            row.status = ProviderStatus.DISABLED.value
            row.version += 1
            await session.execute(
                update(OrganizationRow)
                .where(OrganizationRow.id == organization_id)
                .values(policy_version=str(uuid4()))
            )
            session.add(
                AuthAuditRow(
                    event_type="ai.profile.disabled",
                    user_id=UUID(actor_id),
                    organization_id=organization_id,
                    correlation_id=name,
                    safe_detail=f"kind={row.kind};provider={row.provider}",
                )
            )
            return True

    async def account(
        self, organization_id: str, profile: str, latency_ms: int, units: int, error: str | None
    ) -> None:
        """Persist sanitized request accounting."""
        async with self._sessions() as session, session.begin():
            session.add(
                AIProviderUsageRow(
                    organization_id=organization_id,
                    profile_name=profile,
                    latency_ms=latency_ms,
                    units=units,
                    error_code=error,
                )
            )

    @staticmethod
    def _model(row: AIProviderProfileRow) -> ProviderProfile:
        return ProviderProfile(
            name=row.name,
            provider=row.provider,
            kind=ProviderKind(row.kind),
            model=row.model,
            endpoint=row.endpoint,
            status=ProviderStatus(row.status),
            version=row.version,
            secret_reference=row.secret_reference,
            timeout_seconds=row.timeout_seconds,
            maximum_retries=row.maximum_retries,
            maximum_concurrency=row.maximum_concurrency,
            daily_unit_limit=row.daily_unit_limit,
            allowed_classifications=tuple(json.loads(row.classifications_json)),
            capabilities=tuple(json.loads(row.capabilities_json)),
            routing_priority=row.routing_priority,
        )

    @staticmethod
    def _values(profile: ProviderProfile) -> dict[str, object]:
        return {
            "name": profile.name,
            "kind": profile.kind.value,
            "provider": profile.provider,
            "model": profile.model,
            "endpoint": profile.endpoint,
            "status": ProviderStatus.ENABLED.value,
            "secret_reference": profile.secret_reference,
            "timeout_seconds": int(profile.timeout_seconds),
            "maximum_retries": profile.maximum_retries,
            "maximum_concurrency": profile.maximum_concurrency,
            "daily_unit_limit": profile.daily_unit_limit,
            "classifications_json": json.dumps(profile.allowed_classifications),
            "capabilities_json": json.dumps(profile.capabilities),
            "routing_priority": profile.routing_priority,
        }
