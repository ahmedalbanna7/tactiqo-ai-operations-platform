"""SQLAlchemy canonical knowledge repository and local lexical fallback."""

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from tactiqo.identity.infrastructure.tables import AuthAuditRow
from tactiqo.knowledge.application.chunking import StructureAwareChunker
from tactiqo.knowledge.application.content_security import DocumentContentSecurityScanner
from tactiqo.knowledge.domain.models import (
    CanonicalDocumentElement,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDomain,
    KnowledgePurpose,
    KnowledgeResult,
)
from tactiqo.knowledge.infrastructure.tables import (
    DocumentVersionRow,
    KnowledgeAclSnapshotRow,
    KnowledgeChunkRow,
    KnowledgeDocumentRow,
    KnowledgeElementRow,
    KnowledgeEmbeddingSpaceRow,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import session_scope

_WORD_PATTERN = re.compile(r"\w{3,}", flags=re.UNICODE)


class SqlAlchemyKnowledgeRepository:
    """Own canonical knowledge data and a documented development search fallback."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the repository with a transaction factory."""
        self._sessions = sessions
        self._chunker = StructureAwareChunker()
        self._scanner = DocumentContentSecurityScanner()

    async def create_document(  # noqa: PLR0913 - canonical creation contract
        self,
        *,
        name: str,
        content_type: str,
        storage_key: str,
        checksum_sha256: str,
        context: ExecutionContext,
        project_id: str | None,
        domain: str,
        purpose: str,
        owner_scope: str = "personal",
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
            domain=domain,
            purpose=purpose,
            owner_scope=owner_scope,
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
        owner_scope: str | None = None,
    ) -> list[KnowledgeDocument]:
        """List documents in exact organization scope."""
        statement = (
            select(KnowledgeDocumentRow)
            .where(
                KnowledgeDocumentRow.organization_id == context.organization_id,
                KnowledgeDocumentRow.status != DocumentStatus.REVOKED.value,
                self._document_scope(context),
            )
            .order_by(KnowledgeDocumentRow.updated_at.desc())
            .limit(limit)
        )
        if owner_scope is not None:
            statement = statement.where(KnowledgeDocumentRow.owner_scope == owner_scope)
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._document(row) for row in rows]

    async def promote_document(
        self, document_id: UUID, context: ExecutionContext
    ) -> KnowledgeDocument | None:
        """Atomically change document ownership and its current retrieval snapshot."""
        async with session_scope(self._sessions) as session:
            row = await session.scalar(
                select(KnowledgeDocumentRow).where(
                    KnowledgeDocumentRow.id == document_id,
                    KnowledgeDocumentRow.organization_id == context.organization_id,
                    KnowledgeDocumentRow.actor_id == context.actor_id,
                ).with_for_update()
            )
            if row is None or row.status == DocumentStatus.REVOKED.value:
                return None
            if row.owner_scope != "organization":
                row.owner_scope = "organization"
                row.updated_at = datetime.now(UTC)
                snapshots = (
                    await session.scalars(
                        select(KnowledgeAclSnapshotRow).where(
                            KnowledgeAclSnapshotRow.document_id == document_id
                        )
                    )
                ).all()
                for snapshot in snapshots:
                    snapshot.organization_access = True
                    snapshot.policy_version = context.policy_version
                    acl_payload = {
                        "organization_id": context.organization_id,
                        "organization_access": True,
                        "user_ids": snapshot.user_ids,
                        "department_ids": snapshot.department_ids,
                        "team_ids": snapshot.team_ids,
                        "project_ids": snapshot.project_ids,
                        "policy_version": context.policy_version,
                    }
                    snapshot.source_acl_hash = hashlib.sha256(
                        json.dumps(acl_payload, sort_keys=True).encode()
                    ).hexdigest()
                session.add(AuthAuditRow(
                    event_type="knowledge.document.promoted",
                    user_id=UUID(context.actor_id),
                    organization_id=context.organization_id,
                    correlation_id=str(document_id),
                    safe_detail="owner_scope=organization",
                ))
            await session.flush()
            return self._document(row)

    async def get_document(
        self,
        document_id: UUID,
        context: ExecutionContext | None = None,
    ) -> KnowledgeDocument | None:
        """Get a document and optionally enforce exact organization scope."""
        statement = select(KnowledgeDocumentRow).where(KnowledgeDocumentRow.id == document_id)
        if context is not None:
            statement = statement.where(
                KnowledgeDocumentRow.organization_id == context.organization_id,
                self._document_scope(context),
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
            self._document_scope(context),
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
        context: ExecutionContext,
    ) -> None:
        """Version, ACL-snapshot, chunk, and mark readiness atomically."""
        async with session_scope(self._sessions) as session:
            row = await session.get(KnowledgeDocumentRow, document_id, with_for_update=True)
            if row is None:
                msg = "Knowledge document not found."
                raise LookupError(msg)
            if row.organization_id != context.organization_id or row.actor_id != context.actor_id:
                msg = "Knowledge ingestion authority no longer matches document ownership."
                raise PermissionError(msg)
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
            version = await session.scalar(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.document_id == document_id,
                    DocumentVersionRow.content_hash == row.checksum_sha256,
                )
            )
            if version is None:
                version_number = (
                    int(
                        await session.scalar(
                            select(
                                func.coalesce(func.max(DocumentVersionRow.version_number), 0)
                            ).where(DocumentVersionRow.document_id == document_id)
                        )
                        or 0
                    )
                    + 1
                )
                version = DocumentVersionRow(
                    document_id=document_id,
                    version_number=version_number,
                    content_hash=row.checksum_sha256,
                    parser_name=parser_name,
                    parser_version=parser_version,
                )
                session.add(version)
                await session.flush()
            await session.execute(
                delete(KnowledgeChunkRow).where(KnowledgeChunkRow.version_id == version.id)
            )
            await session.execute(
                delete(KnowledgeAclSnapshotRow).where(
                    KnowledgeAclSnapshotRow.version_id == version.id
                )
            )
            chunks = self._chunker.chunk(list(elements))
            session.add_all(
                [
                    KnowledgeChunkRow(
                        document_id=document_id,
                        version_id=version.id,
                        ordinal=ordinal,
                        text=chunk.text,
                        normalized_text=unicodedata.normalize("NFKC", chunk.text).strip(),
                        language=self._language(chunk.text),
                        token_count=len(chunk.text.split()),
                        locator=chunk.locator,
                        classification=row.classification,
                        security_signals=list(self._scanner.assess(chunk.text).signals),
                    )
                    for ordinal, chunk in enumerate(chunks, start=1)
                ]
            )
            acl_payload = {
                "organization_id": context.organization_id,
                "organization_access": row.owner_scope == "organization",
                "user_ids": [context.actor_id],
                "department_ids": list(context.department_ids),
                "team_ids": list(context.team_ids),
                "project_ids": [row.project_id] if row.project_id else [],
                "policy_version": context.policy_version,
            }
            session.add(
                KnowledgeAclSnapshotRow(
                    document_id=document_id,
                    version_id=version.id,
                    organization_id=context.organization_id,
                    organization_access=row.owner_scope == "organization",
                    user_ids=[context.actor_id],
                    department_ids=list(context.department_ids),
                    team_ids=list(context.team_ids),
                    project_ids=[row.project_id] if row.project_id else [],
                    policy_version=context.policy_version,
                    source_acl_hash=hashlib.sha256(
                        json.dumps(acl_payload, sort_keys=True).encode()
                    ).hexdigest(),
                )
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

    async def revoke_document(
        self, document_id: UUID, context: ExecutionContext
    ) -> KnowledgeDocument | None:
        """Atomically revoke visibility and cascade-delete versions, chunks, vectors, and ACLs."""
        async with session_scope(self._sessions) as session:
            row = await session.scalar(
                select(KnowledgeDocumentRow)
                .where(
                    KnowledgeDocumentRow.id == document_id,
                    KnowledgeDocumentRow.organization_id == context.organization_id,
                    self._document_scope(context),
                )
                .with_for_update()
            )
            if row is None:
                return None
            row.status = DocumentStatus.REVOKED.value
            row.error_code = None
            row.updated_at = datetime.now(UTC)
            await session.execute(
                delete(KnowledgeElementRow).where(KnowledgeElementRow.document_id == document_id)
            )
            await session.execute(
                delete(DocumentVersionRow).where(DocumentVersionRow.document_id == document_id)
            )
            await session.flush()
            await session.refresh(row)
            return self._document(row)

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
                KnowledgeDocumentRow.purpose != KnowledgePurpose.IGNORE.value,
                self._document_scope(context),
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

    async def chunks_for_index(
        self, document_id: UUID, context: ExecutionContext
    ) -> list[KnowledgeChunk]:
        """Return only current-version chunks visible to the delegated actor."""
        statement = (
            select(KnowledgeChunkRow)
            .join(DocumentVersionRow, DocumentVersionRow.id == KnowledgeChunkRow.version_id)
            .join(KnowledgeDocumentRow, KnowledgeDocumentRow.id == KnowledgeChunkRow.document_id)
            .where(
                KnowledgeDocumentRow.id == document_id,
                KnowledgeDocumentRow.organization_id == context.organization_id,
                KnowledgeDocumentRow.status == DocumentStatus.READY.value,
                KnowledgeDocumentRow.purpose != KnowledgePurpose.IGNORE.value,
                DocumentVersionRow.content_hash == KnowledgeDocumentRow.checksum_sha256,
                self._document_scope(context),
            )
            .order_by(KnowledgeChunkRow.ordinal)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [
            KnowledgeChunk(
                id=row.id,
                document_id=row.document_id,
                version_id=row.version_id,
                ordinal=row.ordinal,
                text=row.text,
                normalized_text=row.normalized_text,
                language=row.language,
                token_count=row.token_count,
                locator=row.locator,
                classification=row.classification,
            )
            for row in rows
        ]

    async def upsert_embeddings(  # noqa: PLR0913
        self,
        chunk_ids: Sequence[UUID],
        vectors: Sequence[Sequence[float]],
        space_key: str,
        model: str,
        dimensions: int,
        context: ExecutionContext,
    ) -> None:
        """Upsert vectors without ever mixing embedding spaces or tenants."""
        if len(chunk_ids) != len(vectors) or any(len(vector) != dimensions for vector in vectors):
            message = "embedding_shape_mismatch"
            raise ValueError(message)
        async with session_scope(self._sessions) as session:
            space = await session.scalar(
                select(KnowledgeEmbeddingSpaceRow).where(
                    KnowledgeEmbeddingSpaceRow.organization_id == context.organization_id,
                    KnowledgeEmbeddingSpaceRow.space_key == space_key,
                )
            )
            if space is None:
                space = KnowledgeEmbeddingSpaceRow(
                    organization_id=context.organization_id,
                    space_key=space_key,
                    model=model,
                    dimensions=dimensions,
                )
                session.add(space)
                await session.flush()
            elif space.dimensions != dimensions:
                message = "embedding_space_dimension_mismatch"
                raise ValueError(message)
            for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
                await session.execute(
                    text("""INSERT INTO knowledge_chunk_embeddings
                    (chunk_id, embedding_space_id, embedding) VALUES
                    (:chunk_id, :space_id, CAST(:embedding AS vector))
                    ON CONFLICT (chunk_id, embedding_space_id)
                    DO UPDATE SET embedding = EXCLUDED.embedding, created_at = now()"""),
                    {
                        "chunk_id": chunk_id,
                        "space_id": space.id,
                        "embedding": "[" + ",".join(str(value) for value in vector) + "]",
                    },
                )

    async def hybrid_search(
        self,
        query: str,
        query_vector: Sequence[float],
        space_key: str,
        context: ExecutionContext,
        limit: int,
    ) -> list[KnowledgeResult]:
        """Apply ACLs first, then fuse lexical and semantic ranks using RRF."""
        allowed = self._allowed_classifications(context.classification_clearance)
        params = {
            "organization_id": context.organization_id,
            "actor_id": context.actor_id,
            "departments": list(context.department_ids),
            "teams": list(context.team_ids),
            "projects": list(context.project_ids),
            "allowed": allowed,
            "space_key": space_key,
            "query": query,
            "vector": "[" + ",".join(str(value) for value in query_vector) + "]",
            "candidate_limit": max(limit * 5, 30),
            "limit": limit,
        }
        statement = text("""
        WITH authorized AS (
          SELECT c.id, c.document_id, c.ordinal, c.text, c.locator, d.name,
                 d.source_uri, d.updated_at, e.embedding
          FROM knowledge_chunks c
          JOIN knowledge_document_versions v ON v.id = c.version_id
          JOIN knowledge_documents d ON d.id = c.document_id
          JOIN knowledge_acl_snapshots a ON a.version_id = c.version_id
          JOIN knowledge_embedding_spaces s ON s.organization_id = a.organization_id
                                             AND s.space_key = :space_key
          JOIN knowledge_chunk_embeddings e ON e.chunk_id = c.id
                                             AND e.embedding_space_id = s.id
          WHERE a.organization_id = :organization_id
            AND d.status = 'ready'
            AND d.purpose <> 'ignore'
            AND v.content_hash = d.checksum_sha256
            AND c.classification = ANY(:allowed)
            AND (
              (d.owner_scope = 'personal' AND EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(a.user_ids::jsonb) x WHERE x = :actor_id
              ))
              OR (d.owner_scope = 'organization' AND a.organization_access)
            )
        ), lexical AS (
          SELECT id, row_number() OVER (ORDER BY ts_rank_cd(
            to_tsvector('simple', text), plainto_tsquery('simple', :query)) DESC) AS rank
          FROM authorized
          WHERE to_tsvector('simple', text) @@ plainto_tsquery('simple', :query)
          LIMIT :candidate_limit
        ), semantic AS (
          SELECT id, row_number() OVER (ORDER BY embedding <=> CAST(:vector AS vector)) AS rank
          FROM authorized ORDER BY embedding <=> CAST(:vector AS vector) LIMIT :candidate_limit
        ), fused AS (
          SELECT id, sum(score) AS score FROM (
            SELECT id, 1.0 / (60 + rank) AS score FROM lexical
            UNION ALL SELECT id, 1.0 / (60 + rank) AS score FROM semantic
          ) ranked GROUP BY id
        )
        SELECT a.*, f.score FROM fused f JOIN authorized a ON a.id = f.id
        ORDER BY f.score DESC LIMIT :limit
        """)
        async with self._sessions() as session:
            rows = (await session.execute(statement, params)).mappings().all()
        return [
            KnowledgeResult(
                citation_id=f"{row['document_id']}:{row['ordinal']}",
                document_id=row["document_id"],
                title=row["name"],
                content=row["text"],
                source_uri=row["source_uri"],
                locator=row["locator"],
                freshness=row["updated_at"],
                score=float(row["score"]),
            )
            for row in rows
        ]

    async def preview(
        self,
        document_id: UUID,
        chunk_ordinal: int,
        radius: int,
        context: ExecutionContext,
    ) -> list[KnowledgeResult]:
        """Reauthorize the current version before returning bounded adjacent chunks."""
        if chunk_ordinal < 1 or radius not in {0, 1, 2}:
            message = "invalid_preview_window"
            raise ValueError(message)
        statement = text("""
        SELECT c.document_id, c.ordinal, c.text, c.locator, d.name, d.source_uri, d.updated_at
        FROM knowledge_chunks c
        JOIN knowledge_document_versions v ON v.id = c.version_id
        JOIN knowledge_documents d ON d.id = c.document_id
        JOIN knowledge_acl_snapshots a ON a.version_id = c.version_id
        WHERE d.id = :document_id
          AND a.organization_id = :organization_id
          AND d.status = 'ready'
          AND d.purpose <> 'ignore'
          AND v.content_hash = d.checksum_sha256
          AND c.classification = ANY(:allowed)
          AND c.ordinal BETWEEN :minimum AND :maximum
          AND (
            (d.owner_scope = 'personal' AND EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(a.user_ids::jsonb) x WHERE x = :actor_id
            ))
            OR (d.owner_scope = 'organization' AND a.organization_access)
          )
        ORDER BY c.ordinal
        """)
        params = {
            "document_id": document_id,
            "organization_id": context.organization_id,
            "actor_id": context.actor_id,
            "departments": list(context.department_ids),
            "teams": list(context.team_ids),
            "projects": list(context.project_ids),
            "allowed": self._allowed_classifications(context.classification_clearance),
            "minimum": max(1, chunk_ordinal - radius),
            "maximum": chunk_ordinal + radius,
        }
        async with self._sessions() as session:
            rows = (await session.execute(statement, params)).mappings().all()
        if not any(row["ordinal"] == chunk_ordinal for row in rows):
            return []
        return [
            KnowledgeResult(
                citation_id=f"{row['document_id']}:{row['ordinal']}",
                document_id=row["document_id"],
                title=row["name"],
                content=self._scanner.wrap_as_evidence(row["text"]),
                source_uri=row["source_uri"],
                locator=row["locator"],
                freshness=row["updated_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _allowed_classifications(clearance: str) -> list[str]:
        levels = ["public", "internal", "confidential", "restricted"]
        try:
            return levels[: levels.index(clearance) + 1]
        except ValueError:
            return []

    @staticmethod
    def _language(text: str) -> str:
        """Detect coarse Arabic/English/mixed language without an external model."""
        arabic = sum("\u0600" <= character <= "\u06ff" for character in text)
        latin = sum(character.isascii() and character.isalpha() for character in text)
        if arabic and latin:
            return "mixed"
        if arabic:
            return "ar"
        return "en" if latin else "und"

    @staticmethod
    def _document_scope(context: ExecutionContext) -> ColumnElement[bool]:
        """Build a mandatory owner/project predicate before reading document metadata."""
        classification = KnowledgeDocumentRow.classification.in_(
            SqlAlchemyKnowledgeRepository._allowed_classifications(
                context.classification_clearance
            )
        )
        return and_(
            classification,
            or_(
                and_(
                    KnowledgeDocumentRow.owner_scope == "personal",
                    KnowledgeDocumentRow.actor_id == context.actor_id,
                ),
                KnowledgeDocumentRow.owner_scope == "organization",
            ),
        )

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
            domain=KnowledgeDomain(row.domain),
            purpose=KnowledgePurpose(row.purpose),
            owner_scope=row.owner_scope,
        )
