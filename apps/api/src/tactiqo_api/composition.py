"""F1 runtime composition kept separate from HTTP transport code."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from tactiqo.agents.application.orchestrator import AgentOrchestrator
from tactiqo.agents.application.supervisor import AgentTaskSupervisor
from tactiqo.agents.infrastructure.model_providers import (
    DeterministicModelProvider,
    OpenAIResponsesProvider,
)
from tactiqo.chat.application.service import ChatService
from tactiqo.chat.infrastructure.repositories import SqlAlchemyChatRepository
from tactiqo.integrations.onyx.adapter import OnyxAdapter
from tactiqo.knowledge.application.service import KnowledgeService
from tactiqo.knowledge.infrastructure.object_storage import MinioObjectStorage
from tactiqo.knowledge.infrastructure.queue import RabbitMqIngestionPublisher
from tactiqo.knowledge.infrastructure.repositories import SqlAlchemyKnowledgeRepository
from tactiqo.knowledge.infrastructure.search import (
    FallbackKnowledgeSearch,
    LocalLexicalKnowledgeSearch,
)
from tactiqo.shared.application.authorization import LocalDevelopmentAuthorization
from tactiqo.shared.infrastructure.database import create_database_engine, create_session_factory
from tactiqo.shared.infrastructure.settings import ModelProviderName, Settings
from tactiqo.tools.application.policy import ToolPolicy
from tactiqo.tools.application.service import ApprovalService
from tactiqo.tools.infrastructure.mcp_gateway import DisabledToolGateway, McpToolGateway
from tactiqo.tools.infrastructure.repositories import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyToolAuditRepository,
)

if TYPE_CHECKING:
    from tactiqo.agents.application.ports import ModelProviderPort
    from tactiqo.knowledge.application.ports import KnowledgeSearchPort

Lifespan = Callable[[FastAPI], Any]


def build_lifespan(settings: Settings) -> Lifespan:
    """Build a resource-safe lifespan closure from validated settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(settings.database_url.get_secret_value())
        sessions = create_session_factory(engine)
        chat_repository = SqlAlchemyChatRepository(sessions)
        approval_repository = SqlAlchemyApprovalRepository(sessions)
        audit_repository = SqlAlchemyToolAuditRepository(sessions)
        knowledge_repository = SqlAlchemyKnowledgeRepository(sessions)
        authorization = LocalDevelopmentAuthorization()
        policy = ToolPolicy()

        local_search = LocalLexicalKnowledgeSearch(knowledge_repository)
        knowledge_search: KnowledgeSearchPort
        if settings.knowledge_search_enabled:
            token = settings.onyx_service_token
            if token is None:
                msg = "Validated Onyx token disappeared during composition."
                raise RuntimeError(msg)
            onyx = OnyxAdapter(
                settings.onyx_base_url,
                token.get_secret_value(),
                knowledge_repository,
            )
            knowledge_search = (
                FallbackKnowledgeSearch(onyx, local_search)
                if settings.knowledge_local_fallback_enabled
                else onyx
            )
        else:
            knowledge_search = local_search

        tool_gateway = (
            McpToolGateway(
                settings.mcp_demo_url,
                policy,
                settings.mcp_timeout_seconds,
                settings.mcp_max_result_characters,
            )
            if settings.mcp_enabled
            else DisabledToolGateway()
        )
        model_provider: ModelProviderPort
        if settings.model_provider is ModelProviderName.OPENAI:
            key = settings.openai_api_key
            if key is None:
                msg = "Validated OpenAI key disappeared during composition."
                raise RuntimeError(msg)
            model_provider = OpenAIResponsesProvider(
                key.get_secret_value(),
                settings.openai_model,
                settings.openai_reasoning_effort,
            )
        else:
            model_provider = DeterministicModelProvider()

        async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_dsn) as checkpointer:
            await checkpointer.setup()
            orchestrator = AgentOrchestrator(
                chat_repository=chat_repository,
                approval_repository=approval_repository,
                authorization=authorization,
                model_provider=model_provider,
                knowledge_search=knowledge_search,
                tool_gateway=tool_gateway,
                tool_audit=audit_repository,
                tool_policy=policy,
                checkpointer=checkpointer,
                maximum_tool_calls=settings.agent_max_tool_calls,
                timeout_seconds=settings.agent_timeout_seconds,
            )
            supervisor = AgentTaskSupervisor(
                orchestrator,
                settings.agent_max_concurrent_runs,
            )
            app.state.chat_service = ChatService(
                chat_repository,
                authorization,
                supervisor,
            )
            app.state.approval_service = ApprovalService(
                approval_repository,
                chat_repository,
                supervisor,
            )
            app.state.knowledge_service = KnowledgeService(
                knowledge_repository,
                MinioObjectStorage(
                    settings.minio_endpoint,
                    settings.minio_access_key.get_secret_value(),
                    settings.minio_secret_key.get_secret_value(),
                    settings.minio_bucket,
                ),
                RabbitMqIngestionPublisher(
                    settings.rabbitmq_url.get_secret_value(),
                    settings.ingestion_queue_name,
                    settings.ingestion_dead_letter_queue_name,
                ),
                authorization,
                settings.max_upload_bytes,
            )
            try:
                yield
            finally:
                await supervisor.shutdown()
        await engine.dispose()

    return lifespan
