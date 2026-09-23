"""Contracts for storage, parsing, indexing, search, and ingestion jobs."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from tactiqo.knowledge.domain.models import (
    CanonicalDocumentElement,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeResult,
)
from tactiqo.shared.domain.execution import ExecutionContext


class KnowledgeRepository(Protocol):
    """Store canonical document truth and locally searchable elements."""

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
        """Create an uploaded document record."""

    async def list_documents(
        self,
        context: ExecutionContext,
        limit: int = 100,
        owner_scope: str | None = None,
    ) -> list[KnowledgeDocument]:
        """List visible documents."""

    async def promote_document(
        self, document_id: UUID, context: ExecutionContext
    ) -> KnowledgeDocument | None:
        """Atomically broaden one owned document and its retrieval ACL."""

    async def get_document(
        self,
        document_id: UUID,
        context: ExecutionContext | None = None,
    ) -> KnowledgeDocument | None:
        """Get a document, applying scope when supplied."""

    async def get_by_source_uri(
        self,
        source_uri: str,
        context: ExecutionContext,
    ) -> KnowledgeDocument | None:
        """Resolve an authorized citation source."""

    async def mark_processing(self, document_id: UUID) -> None:
        """Move an uploaded document into parsing."""

    async def mark_ready(
        self,
        document_id: UUID,
        parser_name: str,
        parser_version: str,
        elements: Sequence[CanonicalDocumentElement],
        context: ExecutionContext,
    ) -> None:
        """Atomically replace elements and mark the document ready."""

    async def mark_failed(self, document_id: UUID, error_code: str) -> None:
        """Record a safe processing failure code."""

    async def mark_index_degraded(self, document_id: UUID, error_code: str) -> None:
        """Record derived-index failure without invalidating canonical readiness."""

    async def revoke_document(
        self, document_id: UUID, context: ExecutionContext
    ) -> KnowledgeDocument | None:
        """Withdraw a document and purge every derived retrieval artifact."""

    async def local_search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int,
    ) -> list[KnowledgeResult]:
        """Run the explicit local lexical development fallback."""

    async def chunks_for_index(
        self, document_id: UUID, context: ExecutionContext
    ) -> list[KnowledgeChunk]:
        """Return authorized chunks from the current immutable version."""

    async def upsert_embeddings(  # noqa: PLR0913
        self,
        chunk_ids: Sequence[UUID],
        vectors: Sequence[Sequence[float]],
        space_key: str,
        model: str,
        dimensions: int,
        context: ExecutionContext,
    ) -> None:
        """Persist vectors in one immutable embedding space."""

    async def hybrid_search(
        self,
        query: str,
        query_vector: Sequence[float],
        space_key: str,
        context: ExecutionContext,
        limit: int,
    ) -> list[KnowledgeResult]:
        """Fuse ACL-filtered lexical and vector rankings."""

    async def preview(
        self,
        document_id: UUID,
        chunk_ordinal: int,
        radius: int,
        context: ExecutionContext,
    ) -> list[KnowledgeResult]:
        """Return a bounded, reauthorized window around one cited chunk."""


class ObjectStorage(Protocol):
    """Store and load original document bytes."""

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        """Store an object idempotently."""

    async def get(self, key: str) -> bytes:
        """Load one object."""


class DocumentParser(Protocol):
    """Parse original bytes into canonical elements."""

    async def parse(
        self,
        document_id: UUID,
        name: str,
        content_type: str,
        content: bytes,
    ) -> list[CanonicalDocumentElement]:
        """Return normalized elements with provenance."""


class KnowledgeIndexer(Protocol):
    """Submit canonical elements to a derived search implementation."""

    async def index(
        self,
        document: KnowledgeDocument,
        elements: Sequence[CanonicalDocumentElement],
        context: ExecutionContext,
    ) -> None:
        """Upsert one document in the derived index."""


class KnowledgeSearchPort(Protocol):
    """Retrieve authorized evidence without vendor-specific values."""

    async def search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int = 6,
    ) -> list[KnowledgeResult]:
        """Return evidence already filtered to the execution context."""

    async def list_sources(
        self,
        context: ExecutionContext,
        limit: int = 100,
    ) -> list[KnowledgeResult]:
        """List authorized knowledge sources without searching their contents."""


class IngestionPublisher(Protocol):
    """Publish durable document parsing work."""

    async def publish(self, document_id: UUID, context: ExecutionContext) -> None:
        """Publish one idempotent parse job."""
