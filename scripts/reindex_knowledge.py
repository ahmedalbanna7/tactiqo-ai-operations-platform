"""Rebuild derived knowledge embeddings from canonical current versions."""

import asyncio

from sqlalchemy import select

from tactiqo.ai.application.bank import AIBank
from tactiqo.ai.infrastructure.lm_studio import LMStudioAdapter
from tactiqo.ai.infrastructure.repository import SqlAIProfileRepository
from tactiqo.knowledge.infrastructure.indexer import PgVectorKnowledgeIndexer
from tactiqo.knowledge.infrastructure.repositories import SqlAlchemyKnowledgeRepository
from tactiqo.knowledge.infrastructure.tables import KnowledgeDocumentRow
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import create_database_engine, create_session_factory
from tactiqo.shared.infrastructure.settings import Settings


async def main() -> None:
    """Index every ready document under its original owner and tenant scope."""
    settings = Settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    repository = SqlAlchemyKnowledgeRepository(sessions)
    lm_studio = LMStudioAdapter()
    bank = AIBank(
        SqlAIProfileRepository(sessions),
        {"lm_studio": lm_studio},
        {"lm_studio": lm_studio},
    )
    indexer = PgVectorKnowledgeIndexer(repository, bank)
    async with sessions() as session:
        documents = (
            await session.scalars(
                select(KnowledgeDocumentRow).where(KnowledgeDocumentRow.status == "ready")
            )
        ).all()
    indexed = 0
    try:
        for row in documents:
            context = ExecutionContext(
                actor_id=row.actor_id,
                organization_id=row.organization_id,
                correlation_id=f"reindex-{row.id}",
                classification_clearance=row.classification,
                policy_version="f7-controlled-reindex-v1",
                project_ids=(row.project_id,) if row.project_id else (),
            )
            document = await repository.get_document(row.id, context)
            if document is not None:
                await indexer.index(document, (), context)
                indexed += 1
        print(f"indexed_documents={indexed}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
