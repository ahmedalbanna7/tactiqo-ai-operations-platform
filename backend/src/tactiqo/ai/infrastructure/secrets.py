"""Encrypted local AI credential store; production can replace this with a vault adapter."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.ai.infrastructure.tables import AIProviderCredentialRow
from tactiqo.integrations.application.ports import CredentialCipher


class SqlEncryptedAISecretStore:
    """Persist authenticated ciphertext while exposing only opaque references."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        cipher: CredentialCipher,
    ) -> None:
        """Configure tenant persistence and authenticated encryption."""
        self._sessions = sessions
        self._cipher = cipher

    async def put(self, organization_id: str, provider: str, secret: str, actor_id: str) -> str:
        """Encrypt provider material and return a random reference."""
        reference = f"aisec_{uuid4().hex}"
        row = AIProviderCredentialRow(
            organization_id=organization_id,
            reference=reference,
            provider=provider,
            encrypted_secret=self._cipher.encrypt(secret),
            last_four=secret[-4:],
            created_by=actor_id,
        )
        async with self._sessions() as session, session.begin():
            session.add(row)
        return reference

    async def resolve(self, reference: str) -> str | None:
        """Decrypt one active opaque reference without returning metadata."""
        async with self._sessions() as session:
            row = await session.scalar(
                select(AIProviderCredentialRow).where(
                    AIProviderCredentialRow.reference == reference,
                    AIProviderCredentialRow.active.is_(True),
                )
            )
        return self._cipher.decrypt(row.encrypted_secret) if row else None

    async def belongs_to(self, reference: str, organization_id: str, provider: str) -> bool:
        """Fail closed when an opaque reference crosses tenant or provider scope."""
        async with self._sessions() as session:
            row = await session.scalar(
                select(AIProviderCredentialRow.id).where(
                    AIProviderCredentialRow.reference == reference,
                    AIProviderCredentialRow.organization_id == organization_id,
                    AIProviderCredentialRow.provider == provider,
                    AIProviderCredentialRow.active.is_(True),
                )
            )
        return row is not None
