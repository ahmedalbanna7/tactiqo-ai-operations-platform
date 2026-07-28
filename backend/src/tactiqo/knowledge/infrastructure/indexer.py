"""Explicit no-op derived index used when Onyx is disabled."""

from collections.abc import Sequence

from tactiqo.knowledge.domain.models import CanonicalDocumentElement, KnowledgeDocument


class DisabledKnowledgeIndexer:
    """Keep canonical ingestion usable while declaring derived search disabled."""

    async def index(
        self,
        document: KnowledgeDocument,
        elements: Sequence[CanonicalDocumentElement],
    ) -> None:
        """Intentionally perform no derived indexing."""
        del document, elements
