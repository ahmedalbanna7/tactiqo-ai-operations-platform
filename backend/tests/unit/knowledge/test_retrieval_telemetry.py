"""Retrieval observability distinguishes hybrid success from declared fallback."""

import asyncio

from tactiqo.knowledge.application.telemetry import RetrievalMetrics
from tactiqo.knowledge.infrastructure.search import FallbackKnowledgeSearch
from tactiqo.shared.domain.execution import ExecutionContext


class SearchStub:
    """Simple primary/fallback implementation with controllable failure."""

    def __init__(self, *, fail: bool = False) -> None:
        """Set whether the adapter should raise an error."""
        self.fail = fail

    async def search(self, query: str, _context: ExecutionContext, _limit: int = 6) -> list:
        """Return an empty result or simulate a search adapter failure."""
        if self.fail:
            raise RuntimeError(query)
        return []

    async def list_sources(
        self, _context: ExecutionContext, _limit: int = 100
    ) -> list:
        """Return an empty source list for inventory tests."""
        return []


def test_fallback_metrics_track_path_without_query_or_customer_data() -> None:
    """A primary failure followed by local search is visible as fallback, not raw error."""
    metrics = RetrievalMetrics()
    search = FallbackKnowledgeSearch(SearchStub(fail=True), SearchStub(), metrics)
    context = ExecutionContext("actor", "tenant-secret", "correlation", "internal", "test")
    asyncio.run(search.search("private search phrase", context))

    rendered = metrics.render_prometheus()

    assert (
        'tactiqo_knowledge_retrieval_total{operation="search",outcome="fallback"} 1'
    ) in rendered
    assert "private search phrase" not in rendered
    assert "tenant-secret" not in rendered


def test_successful_primary_retrieval_is_distinguished() -> None:
    """Healthy hybrid retrieval is counted separately from degraded fallback."""
    metrics = RetrievalMetrics()
    search = FallbackKnowledgeSearch(SearchStub(), SearchStub(), metrics)
    context = ExecutionContext("actor", "org", "correlation", "internal", "test")
    asyncio.run(search.search("query", context))

    assert (
        'tactiqo_knowledge_retrieval_total{operation="search",outcome="primary"} 1'
    ) in metrics.render_prometheus()
