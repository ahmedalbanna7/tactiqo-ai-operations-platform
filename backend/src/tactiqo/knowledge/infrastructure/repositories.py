"""SQLAlchemy canonical knowledge repository and local lexical fallback."""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.knowledge.domain.models import (
    CanonicalDocumentElement,
    DocumentStatus,
    KnowledgeDocument,
    KnowledgeResult,
)
from tactiqo.knowledge.infrastructure.tables import KnowledgeDocumentRow, KnowledgeElementRow
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import session_scope

_WORD_PATTERN = re.compile(r"\w{3,}", flags=re.UNICODE)


class SqlAlchemyKnowledgeRepository:
    """Own canonical knowledge data and a documented development search fallback."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the repository with a transaction factory."""
        self._sessions = sessions

    async def create_document(  # noqa: PLR0913 - canonical creation contract
        self,
        *,
        name: str,
        content_type: str,
        storage_key: str,
        checksum_sha256: str,
        context: ExecutionContext,
        project_id: str | None,
    ) -> KnowledgeDocument:
        """Create a scoped document with a stable citation URI."""
        row = KnowledgeDocumentRow(
            name=name,
            content_type=content_type,
            storage_key=storage_key,
            source_uri="pending",
            checksum_sha256=checksum_sha256,
            status=DocumentStatus.UPLOADED.value,
            actor_id=context.actor_id,
            organization_id=context.organization_id,
            classification=context.classification_clearance,
            project_id=project_id,
        )
        async with session_scope(self._sessions) as session:
            session.add(row)
            await session.flush()
            row.source_uri = f"tactiqo://knowledge/{row.id}"
            await session.flush()
            await session.refresh(row)
        return self._document(row)

    async def list_documents(
        self,
        context: ExecutionContext,
        limit: int = 100,
    ) -> list[KnowledgeDocument]:
        """List documents in exact organization scope."""
        statement = (
            select(KnowledgeDocumentRow)
            .where(KnowledgeDocumentRow.organization_id == context.organization_id)
            .order_by(KnowledgeDocumentRow.updated_at.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._document(row) for row in rows]

    async def get_document(
        self,
        document_id: UUID,
        context: ExecutionContext | None = None,
    ) -> KnowledgeDocument | None:
        """Get a document and optionally enforce exact organization scope."""
        statement = select(KnowledgeDocumentRow).where(KnowledgeDocumentRow.id == document_id)
        if context is not None:
            statement = statement.where(
                KnowledgeDocumentRow.organization_id == context.organization_id
            )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        return self._document(row) if row is not None else None

    async def get_by_source_uri(
        self,
        source_uri: str,
        context: ExecutionContext,
    ) -> KnowledgeDocument | None:
        """Resolve citations fail-closed through platform-owned scope metadata."""
        statement = select(KnowledgeDocumentRow).where(
            KnowledgeDocumentRow.source_uri == source_uri,
            KnowledgeDocumentRow.organization_id == context.organization_id,
            KnowledgeDocumentRow.status == DocumentStatus.READY.value,
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        return self._document(row) if row is not None else None

    async def mark_processing(self, document_id: UUID) -> None:
        """Persist the parsing transition before processing bytes."""
        await self._set_status(document_id, DocumentStatus.PROCESSING)

    async def mark_ready(
        self,
        document_id: UUID,
        parser_name: str,
        parser_version: str,
        elements: Sequence[CanonicalDocumentElement],
    ) -> None:
        """Replace canonical elements and mark readiness atomically."""
        async with session_scope(self._sessions) as session:
            row = await session.get(KnowledgeDocumentRow, document_id, with_for_update=True)
            if row is None:
                msg = "Knowledge document not found."
                raise LookupError(msg)
            await session.execute(
                delete(KnowledgeElementRow).where(KnowledgeElementRow.document_id == document_id)
            )
            session.add_all(
                [
                    KnowledgeElementRow(
                        id=element.id,
                        document_id=document_id,
                        ordinal=element.ordinal,
                        element_type=element.element_type,
                        text=element.text,
                        locator=element.locator,
                    )
                    for element in elements
                ]
            )
            row.status = DocumentStatus.READY.value
            row.parser_name = parser_name
            row.parser_version = parser_version
            row.error_code = None
            row.updated_at = datetime.now(UTC)

    async def mark_failed(self, document_id: UUID, error_code: str) -> None:
        """Record a redacted failure code while retaining the original file."""
        async with session_scope(self._sessions) as session:
            row = await session.get(KnowledgeDocumentRow, document_id, with_for_update=True)
            if row is None:
                return
            row.status = DocumentStatus.FAILED.value
            row.error_code = error_code
            row.updated_at = datetime.now(UTC)

    async def mark_index_degraded(self, document_id: UUID, error_code: str) -> None:
        """Keep canonical content ready while exposing derived-index degradation."""
        async with session_scope(self._sessions) as session:
            row = await session.get(KnowledgeDocumentRow, document_id, with_for_update=True)
            if row is None:
                return
            row.error_code = error_code
            row.updated_at = datetime.now(UTC)

    async def local_search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int,
    ) -> list[KnowledgeResult]:
        """Use bounded lexical matching only when the local fallback is explicit."""
        terms = list(dict.fromkeys(word.lower() for word in _WORD_PATTERN.findall(query)))[:8]
        if not terms:
            return []
        conditions = [KnowledgeElementRow.text.ilike(f"%{term}%") for term in terms]
        statement = (
            select(KnowledgeElementRow, KnowledgeDocumentRow)
            .join(
                KnowledgeDocumentRow,
                KnowledgeDocumentRow.id == KnowledgeElementRow.document_id,
            )
            .where(
                KnowledgeDocumentRow.organization_id == context.organization_id,
                KnowledgeDocumentRow.status == DocumentStatus.READY.value,
                or_(*conditions),
            )
            .order_by(KnowledgeDocumentRow.updated_at.desc(), KnowledgeElementRow.ordinal)
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            KnowledgeResult(
                citation_id=f"{document.id}:{element.ordinal}",
                document_id=document.id,
                title=document.name,
                content=element.text,
                source_uri=document.source_uri,
                locator=element.locator,
                freshness=document.updated_at,
            )
            for element, document in rows
        ]

    async def _set_status(self, document_id: UUID, status: DocumentStatus) -> None:
        async with session_scope(self._sessions) as session:
            row = await session.get(KnowledgeDocumentRow, document_id, with_for_update=True)
            if row is None:
                msg = "Knowledge document not found."
                raise LookupError(msg)
            row.status = status.value
            row.updated_at = datetime.now(UTC)

    @staticmethod
    def _document(row: KnowledgeDocumentRow) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=row.id,
            name=row.name,
            content_type=row.content_type,
            storage_key=row.storage_key,
            source_uri=row.source_uri,
            checksum_sha256=row.checksum_sha256,
            status=DocumentStatus(row.status),
            actor_id=row.actor_id,
            organization_id=row.organization_id,
            classification=row.classification,
            project_id=row.project_id,
            parser_name=row.parser_name,
            parser_version=row.parser_version,
            error_code=row.error_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
