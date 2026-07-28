"""Knowledge search adapters and explicit fallback composition."""

from tactiqo.knowledge.application.ports import KnowledgeRepository, KnowledgeSearchPort
from tactiqo.knowledge.domain.models import KnowledgeResult
from tactiqo.shared.domain.execution import ExecutionContext


class LocalLexicalKnowledgeSearch:
    """Development-only search over canonical PostgreSQL elements."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        """Configure canonical PostgreSQL retrieval."""
        self._repository = repository

    async def search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int = 6,
    ) -> list[KnowledgeResult]:
        """Delegate to the scope-filtered local lexical query."""
        return await self._repository.local_search(query, context, limit)


class FallbackKnowledgeSearch:
    """Use a declared fallback only on provider failure, never silently."""

    def __init__(
        self,
        primary: KnowledgeSearchPort,
        fallback: KnowledgeSearchPort,
    ) -> None:
        """Configure a primary provider and declared fallback."""
        self._primary = primary
        self._fallback = fallback

    async def search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int = 6,
    ) -> list[KnowledgeResult]:
        """Return primary results or explicitly degraded local results."""
        try:
            return await self._primary.search(query, context, limit)
        except Exception:  # noqa: BLE001 - adapter boundary converts provider failure
            return await self._fallback.search(query, context, limit)
