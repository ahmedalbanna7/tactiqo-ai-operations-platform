"""Derived knowledge index adapters."""

from collections.abc import Sequence

from tactiqo.ai.application.bank import AIBank
from tactiqo.knowledge.application.ports import KnowledgeRepository
from tactiqo.knowledge.domain.models import CanonicalDocumentElement, KnowledgeDocument
from tactiqo.shared.domain.execution import ExecutionContext


class PgVectorKnowledgeIndexer:
    """Create embeddings through the bank and store them in isolated spaces."""

    def __init__(self, repository: KnowledgeRepository, ai_bank: AIBank) -> None:
        """Configure canonical storage and provider-neutral embeddings."""
        self._repository = repository
        self._ai_bank = ai_bank

    async def index(
        self,
        document: KnowledgeDocument,
        elements: Sequence[CanonicalDocumentElement],
        context: ExecutionContext,
    ) -> None:
        """Embed current-version chunks in bounded batches."""
        del elements
        chunks = await self._repository.chunks_for_index(document.id, context)
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset : offset + 64]
            embedded = await self._ai_bank.embed(
                [chunk.normalized_text for chunk in batch], context
            )
            await self._repository.upsert_embeddings(
                [chunk.id for chunk in batch],
                embedded.vectors,
                embedded.embedding_space_id,
                embedded.model,
                embedded.dimensions,
                context,
            )


class DisabledKnowledgeIndexer:
    """Keep canonical ingestion usable while declaring derived search disabled."""

    async def index(
        self,
        document: KnowledgeDocument,
        elements: Sequence[CanonicalDocumentElement],
        context: ExecutionContext,
    ) -> None:
        """Intentionally perform no derived indexing."""
        del document, elements, context
