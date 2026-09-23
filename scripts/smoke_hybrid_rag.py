"""Run a local end-to-end hybrid RAG smoke test."""

import asyncio

from tactiqo.ai.application.bank import AIBank
from tactiqo.ai.infrastructure.lm_studio import LMStudioAdapter
from tactiqo.ai.infrastructure.repository import SqlAIProfileRepository
from tactiqo.knowledge.infrastructure.repositories import SqlAlchemyKnowledgeRepository
from tactiqo.knowledge.infrastructure.search import HybridKnowledgeSearch
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import create_database_engine, create_session_factory
from tactiqo.shared.infrastructure.settings import Settings


async def main() -> None:
    """Assert Arabic semantic retrieval returns a scoped citation."""
    settings = Settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    adapter = LMStudioAdapter()
    search = HybridKnowledgeSearch(
        SqlAlchemyKnowledgeRepository(sessions),
        AIBank(SqlAIProfileRepository(sessions), {"lm_studio": adapter}, {"lm_studio": adapter}),
    )
    context = ExecutionContext(
        actor_id="00000000-0000-4000-8000-000000000001",
        organization_id="local-dev-organization",
        correlation_id="f7-hybrid-smoke",
        classification_clearance="internal",
        policy_version="f7-smoke-v1",
    )
    try:
        results = await search.search("كيف تعمل صلاحيات المستندات والفهرسة؟", context, 3)
        if not results:
            message = "hybrid_search_returned_no_results"
            raise RuntimeError(message)
        print(f"results={len(results)} citation={results[0].citation_id} title={results[0].title}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
