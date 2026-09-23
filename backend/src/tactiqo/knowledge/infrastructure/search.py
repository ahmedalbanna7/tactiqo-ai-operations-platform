"""Knowledge search adapters and explicit fallback composition."""

from time import monotonic

from tactiqo.ai.application.bank import AIBank
from tactiqo.knowledge.application.content_security import DocumentContentSecurityScanner
from tactiqo.knowledge.application.ports import KnowledgeRepository, KnowledgeSearchPort
from tactiqo.knowledge.application.telemetry import RetrievalMetrics
from tactiqo.knowledge.domain.models import KnowledgeResult
from tactiqo.shared.domain.execution import ExecutionContext


class HybridKnowledgeSearch:
    """Retrieve by lexical and semantic rank after repository-enforced ACL filtering."""

    def __init__(self, repository: KnowledgeRepository, ai_bank: AIBank) -> None:
        """Configure the secure repository and replaceable embedding bank."""
        self._repository = repository
        self._ai_bank = ai_bank
        self._scanner = DocumentContentSecurityScanner()

    async def search(
        self, query: str, context: ExecutionContext, limit: int = 6
    ) -> list[KnowledgeResult]:
        """Embed the query and return wrapped, authorized fused evidence."""
        embedded = await self._ai_bank.embed([query], context)
        results = await self._repository.hybrid_search(
            query, embedded.vectors[0], embedded.embedding_space_id, context, limit
        )
        return self._safe_results(results)

    async def list_sources(
        self, context: ExecutionContext, limit: int = 100
    ) -> list[KnowledgeResult]:
        """List authorized source metadata without semantic retrieval."""
        return await LocalLexicalKnowledgeSearch(self._repository).list_sources(context, limit)

    def _safe_results(self, results: list[KnowledgeResult]) -> list[KnowledgeResult]:
        safe: list[KnowledgeResult] = []
        for item in results:
            content = self._scanner.model_evidence(item.content)
            if content is not None:
                safe.append(
                    KnowledgeResult(
                        citation_id=item.citation_id,
                        document_id=item.document_id,
                        title=item.title,
                        content=content,
                        source_uri=item.source_uri,
                        locator=item.locator,
                        freshness=item.freshness,
                        score=item.score,
                    )
                )
        return safe


class LocalLexicalKnowledgeSearch:
    """Development-only search over canonical PostgreSQL elements."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        """Configure canonical PostgreSQL retrieval."""
        self._repository = repository
        self._scanner = DocumentContentSecurityScanner()

    async def search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int = 6,
    ) -> list[KnowledgeResult]:
        """Delegate to the scope-filtered local lexical query."""
        results = await self._repository.local_search(query, context, limit)
        safe: list[KnowledgeResult] = []
        for item in results:
            content = self._scanner.model_evidence(item.content)
            if content is not None:
                safe.append(
                    KnowledgeResult(
                        citation_id=item.citation_id,
                        document_id=item.document_id,
                        title=item.title,
                        content=content,
                        source_uri=item.source_uri,
                        locator=item.locator,
                        freshness=item.freshness,
                        score=item.score,
                    )
                )
        return safe

    async def list_sources(
        self,
        context: ExecutionContext,
        limit: int = 100,
    ) -> list[KnowledgeResult]:
        """Return document metadata so inventory questions never search file content."""
        documents = await self._repository.list_documents(context, limit)
        return [
            KnowledgeResult(
                citation_id=f"document-{document.id}",
                document_id=document.id,
                title=document.name,
                content=(
                    f"content_type={document.content_type}; status={document.status.value}; "
                    f"domain={document.domain.value}; purpose={document.purpose.value}"
                ),
                source_uri=document.source_uri,
                locator={"kind": "document", "document_id": str(document.id)},
                freshness=document.updated_at,
                score=None,
            )
            for document in documents
        ]


class FallbackKnowledgeSearch:
    """Use a declared fallback only on provider failure, never silently."""

    def __init__(
        self,
        primary: KnowledgeSearchPort,
        fallback: KnowledgeSearchPort,
        metrics: RetrievalMetrics | None = None,
    ) -> None:
        """Configure a primary provider and declared fallback."""
        self._primary = primary
        self._fallback = fallback
        self._metrics = metrics or RetrievalMetrics()

    def render_metrics(self) -> str:
        """Expose bounded retrieval metrics for the protected process scrape."""
        return self._metrics.render_prometheus()

    async def search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int = 6,
    ) -> list[KnowledgeResult]:
        """Return primary results or explicitly degraded local results."""
        started = monotonic()
        outcome = "failure"
        try:
            try:
                result = await self._primary.search(query, context, limit)
            except Exception:  # noqa: BLE001 - adapter boundary converts provider failure
                outcome = "fallback"
                try:
                    return await self._fallback.search(query, context, limit)
                except Exception:
                    outcome = "failure"
                    raise
            else:
                outcome = "primary"
                return result
        finally:
            self._metrics.observe("search", outcome, (monotonic() - started) * 1000)

    async def list_sources(
        self,
        context: ExecutionContext,
        limit: int = 100,
    ) -> list[KnowledgeResult]:
        """Preserve explicit degradation semantics for authorized source inventory."""
        started = monotonic()
        outcome = "failure"
        try:
            try:
                result = await self._primary.list_sources(context, limit)
            except Exception:  # noqa: BLE001 - adapter boundary converts provider failure
                outcome = "fallback"
                try:
                    return await self._fallback.list_sources(context, limit)
                except Exception:
                    outcome = "failure"
                    raise
            else:
                outcome = "primary"
                return result
        finally:
            self._metrics.observe("list_sources", outcome, (monotonic() - started) * 1000)
