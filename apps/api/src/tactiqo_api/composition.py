"""F1 runtime composition kept separate from HTTP transport code."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata
from pydantic import AnyUrl
from sqlalchemy import select

from tactiqo.agents.application.orchestrator import AgentOrchestrator
from tactiqo.agents.application.supervisor import AgentTaskSupervisor
from tactiqo.agents.catalog.application.administration import (
    AgentCatalogAdministrationService,
)
from tactiqo.agents.catalog.application.service import AgentCatalogService
from tactiqo.agents.catalog.domain.models import INITIAL_AGENT_PACKS
from tactiqo.agents.catalog.infrastructure.administration import (
    SqlAgentCatalogAdministrationRepository,
)
from tactiqo.agents.catalog.infrastructure.repository import SqlAgentCatalogRepository
from tactiqo.agents.catalog.infrastructure.tables import (
    AgentActionGrantRow,
    AgentAssignmentRow,
    AgentDefinitionRow,
    AgentVersionRow,
    OrganizationAgentRow,
)
from tactiqo.agents.infrastructure.model_providers import (
    DeterministicModelProvider,
    OpenAIResponsesProvider,
)
from tactiqo.ai.application.bank import AIBank
from tactiqo.ai.infrastructure.claude import ClaudeAdapter
from tactiqo.ai.infrastructure.lm_studio import LMStudioAdapter
from tactiqo.ai.infrastructure.openai_compatible import OpenAICompatibleAdapter
from tactiqo.ai.infrastructure.repository import SqlAIProfileRepository
from tactiqo.ai.infrastructure.secrets import SqlEncryptedAISecretStore
from tactiqo.ai.infrastructure.tables import AIProviderProfileRow
from tactiqo.artifacts.application.execution import (
    ArtifactExecutionService,
    DryRunActionProvider,
    McpActionProvider,
)
from tactiqo.artifacts.application.native_renderers import (
    ExcelWorkbookRenderer,
    PowerPointRenderer,
    WordDocumentRenderer,
)
from tactiqo.artifacts.application.renderers import ArtifactRendererRegistry, TextArtifactRenderer
from tactiqo.artifacts.application.service import ArtifactService
from tactiqo.artifacts.domain.models import ArtifactType
from tactiqo.artifacts.infrastructure.repository import SqlArtifactRepository
from tactiqo.authorization.application.compiler import PolicyCompiler
from tactiqo.authorization.application.preview import EffectiveAccessPreviewService
from tactiqo.authorization.infrastructure.adapters import (
    BoundedDecisionCache,
    SqlDecisionAudit,
    SqlPolicyRepository,
)
from tactiqo.chat.application.service import ChatService
from tactiqo.chat.infrastructure.repositories import SqlAlchemyChatRepository
from tactiqo.identity.application.administration import OrganizationAdministrationService
from tactiqo.identity.application.invitations import OrganizationInvitationService
from tactiqo.identity.application.lifecycle import TenantLifecycleService
from tactiqo.identity.infrastructure.access_preview import SqlAccessPreviewUnitReader
from tactiqo.identity.infrastructure.administration import SqlOrganizationAdministrationRepository
from tactiqo.identity.infrastructure.context import SqlExecutionContextResolver
from tactiqo.identity.infrastructure.invitations import SqlInvitationRepository
from tactiqo.identity.infrastructure.lifecycle import SqlTenantLifecycleRepository
from tactiqo.identity.infrastructure.oidc import OidcIdentityProvider, RemoteJwksProvider
from tactiqo.identity.infrastructure.sessions import OidcLoginCoordinator, SqlSessionService
from tactiqo.identity.infrastructure.tables import (
    OrganizationMemberRow,
    OrganizationRow,
    RoleAssignmentRow,
    UserRow,
)
from tactiqo.integrations.application.service import IntegrationConnectionService
from tactiqo.integrations.infrastructure.crypto import FernetCredentialCipher
from tactiqo.integrations.infrastructure.gateway import (
    McpConnectionGatewayFactory,
    TenantMcpToolGateway,
)
from tactiqo.integrations.infrastructure.oauth import (
    OAuthCredentialResolver,
    OAuthFlowCoordinator,
)
from tactiqo.integrations.infrastructure.repository import (
    SqlAlchemyIntegrationConnectionRepository,
)
from tactiqo.integrations.infrastructure.tool_access_preview import SqlEffectiveToolAccessReader
from tactiqo.jobs.application.service import JobService
from tactiqo.jobs.infrastructure.queue import RabbitJobPublisher
from tactiqo.jobs.infrastructure.repository import SqlAlchemyJobRepository
from tactiqo.knowledge.application.service import KnowledgeService
from tactiqo.knowledge.application.telemetry import (
    IngestionQueueMetrics,
    ObjectStorageMetrics,
    RetrievalMetrics,
)
from tactiqo.knowledge.infrastructure.object_storage import MinioObjectStorage
from tactiqo.knowledge.infrastructure.queue import RabbitMqIngestionPublisher
from tactiqo.knowledge.infrastructure.repositories import SqlAlchemyKnowledgeRepository
from tactiqo.knowledge.infrastructure.search import (
    FallbackKnowledgeSearch,
    HybridKnowledgeSearch,
    LocalLexicalKnowledgeSearch,
)
from tactiqo.shared.application.authorization import LocalDevelopmentAuthorization
from tactiqo.shared.infrastructure.database import create_database_engine, create_session_factory
from tactiqo.shared.infrastructure.settings import ModelProviderName, Settings
from tactiqo.shared.infrastructure.work_envelope import WorkEnvelopeSigner
from tactiqo.tools.application.policy import ToolPolicy
from tactiqo.tools.application.service import ApprovalService
from tactiqo.tools.application.telemetry import ToolCallMetrics
from tactiqo.tools.infrastructure.mcp_gateway import (
    CompositeMcpToolGateway,
    DisabledToolGateway,
    McpToolGateway,
)
from tactiqo.tools.infrastructure.oauth_storage import JsonOAuthTokenStorage
from tactiqo.tools.infrastructure.repositories import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyToolAuditRepository,
)
from tactiqo.tools.infrastructure.telemetry import InstrumentedToolGateway

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tactiqo.agents.application.ports import ModelProviderPort
    from tactiqo.ai.application.ports import EmbeddingAdapter, LLMAdapter
    from tactiqo.knowledge.application.ports import KnowledgeSearchPort
    from tactiqo.tools.application.ports import ToolGateway

Lifespan = Callable[[FastAPI], Any]


async def _ensure_local_identity(  # noqa: C901, PLR0912
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Create the isolated local Owner tenant after migrations, never in shared envs."""
    if not settings.local_development_context_enabled:
        return
    from uuid import UUID  # noqa: PLC0415 - keeps runtime-only bootstrap local

    actor_id = UUID(settings.local_actor_id)
    async with sessions() as session, session.begin():
        user = await session.get(UserRow, actor_id)
        if user is None:
            session.add(
                UserRow(
                    id=actor_id,
                    provider="local-development",
                    subject=str(actor_id),
                    display_name="Local Development Owner",
                )
            )
        organization = await session.get(OrganizationRow, settings.local_organization_id)
        if organization is None:
            session.add(
                OrganizationRow(
                    id=settings.local_organization_id,
                    slug=settings.local_organization_id,
                    name="Tactiqo Local Development",
                    owner_user_id=actor_id,
                )
            )
        await session.flush()
        member = await session.get(
            OrganizationMemberRow,
            (settings.local_organization_id, actor_id),
        )
        if member is None:
            session.add(
                OrganizationMemberRow(
                    organization_id=settings.local_organization_id,
                    user_id=actor_id,
                    status="active",
                )
            )
        owner_role = await session.scalar(
            select(RoleAssignmentRow.id).where(
                RoleAssignmentRow.organization_id == settings.local_organization_id,
                RoleAssignmentRow.user_id == actor_id,
                RoleAssignmentRow.role_code == "owner",
                RoleAssignmentRow.revoked_at.is_(None),
            )
        )
        if owner_role is None:
            session.add(
                RoleAssignmentRow(
                    organization_id=settings.local_organization_id,
                    user_id=actor_id,
                    role_code="owner",
                    assigned_by=actor_id,
                )
            )
        for definition in INITIAL_AGENT_PACKS:
            registered = await session.get(AgentDefinitionRow, definition.code)
            if registered is None:
                session.add(
                    AgentDefinitionRow(
                        code=definition.code,
                        name=definition.name,
                        description=definition.description,
                        category=definition.category.value,
                    )
                )
                await session.flush()
            version = await session.get(AgentVersionRow, (definition.code, "1.0.0"))
            if version is None:
                session.add(
                    AgentVersionRow(
                        agent_code=definition.code,
                        version="1.0.0",
                        prompt_template=(
                            "Built-in governed agent. Follow assigned policy and tools."
                        ),
                        risk="medium",
                    )
                )
                await session.flush()
            installed = await session.get(
                OrganizationAgentRow,
                (settings.local_organization_id, definition.code),
            )
            if installed is None:
                session.add(
                    OrganizationAgentRow(
                        organization_id=settings.local_organization_id,
                        agent_code=definition.code,
                        version="1.0.0",
                        enabled=True,
                        installed_by=actor_id,
                    )
                )
                await session.flush()
            assignment = await session.scalar(
                select(AgentAssignmentRow).where(
                    AgentAssignmentRow.organization_id == settings.local_organization_id,
                    AgentAssignmentRow.agent_code == definition.code,
                    AgentAssignmentRow.target_type == "role",
                    AgentAssignmentRow.target_id == "owner",
                    AgentAssignmentRow.active.is_(True),
                )
            )
            if assignment is None:
                assignment = AgentAssignmentRow(
                    organization_id=settings.local_organization_id,
                    agent_code=definition.code,
                    target_type="role",
                    target_id="owner",
                    classification_ceiling="restricted",
                    assigned_by=actor_id,
                )
                session.add(assignment)
                await session.flush()
                for action in ("visible", "use", "read", "draft", "execute", "administer"):
                    session.add(
                        AgentActionGrantRow(
                            organization_id=settings.local_organization_id,
                            assignment_id=assignment.id,
                            action=action,
                            effect="allow",
                        )
                    )
        for name, kind, model in (
            ("default_reasoning_llm", "llm", "tactiqo-chat"),
            ("multilingual_embedding_model", "embedding", "tactiqo-embedding"),
        ):
            profile = await session.scalar(
                select(AIProviderProfileRow).where(
                    AIProviderProfileRow.organization_id == settings.local_organization_id,
                    AIProviderProfileRow.name == name,
                )
            )
            if profile is None:
                session.add(
                    AIProviderProfileRow(
                        organization_id=settings.local_organization_id,
                        name=name,
                        kind=kind,
                        provider="lm_studio",
                        model=model,
                        endpoint="http://host.docker.internal:1234/v1",
                        status="enabled",
                        timeout_seconds=120,
                        maximum_retries=1,
                        maximum_concurrency=1,
                        daily_unit_limit=1_000_000,
                        classifications_json='["public","internal","confidential","restricted"]',
                    )
                )


def _build_oidc_login(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[SqlSessionService, OidcLoginCoordinator | None]:
    """Compose optional OIDC login separately from the application lifespan."""
    session_service = SqlSessionService(sessions, settings.oidc_session_ttl_seconds)
    if not settings.oidc_enabled:
        return session_service, None
    client_id = settings.oidc_client_id
    client_secret = settings.oidc_client_secret
    state_key = settings.oidc_state_signing_key
    if client_id is None or client_secret is None or state_key is None:
        message = "OIDC is enabled without complete client secrets."
        raise RuntimeError(message)
    coordinator = OidcLoginCoordinator(
        settings.oidc_authorization_endpoint,
        settings.oidc_token_endpoint,
        client_id.get_secret_value(),
        client_secret.get_secret_value(),
        settings.oidc_redirect_uri,
        state_key.get_secret_value(),
        OidcIdentityProvider(
            settings.oidc_issuer,
            settings.oidc_audience,
            RemoteJwksProvider(settings.oidc_jwks_uri),
        ),
        session_service,
    )
    return session_service, coordinator


def build_lifespan(settings: Settings) -> Lifespan:  # noqa: C901, PLR0915
    """Build a resource-safe lifespan closure from validated settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: C901, PLR0912, PLR0915
        engine = create_database_engine(settings.database_url.get_secret_value())
        sessions = create_session_factory(engine)
        await _ensure_local_identity(settings, sessions)
        policy_compiler = PolicyCompiler(
            SqlPolicyRepository(sessions),
            SqlDecisionAudit(sessions),
            BoundedDecisionCache(),
        )
        app.state.agent_catalog_service = AgentCatalogService(
            SqlAgentCatalogRepository(sessions), policy_compiler
        )
        app.state.agent_catalog_administration_service = AgentCatalogAdministrationService(
            SqlAgentCatalogAdministrationRepository(sessions)
        )
        app.state.identity_context_resolver = SqlExecutionContextResolver(sessions)
        app.state.organization_administration_service = OrganizationAdministrationService(
            SqlOrganizationAdministrationRepository(sessions)
        )
        app.state.organization_invitation_service = OrganizationInvitationService(
            SqlInvitationRepository(sessions)
        )
        app.state.tenant_lifecycle_service = TenantLifecycleService(
            SqlTenantLifecycleRepository(sessions)
        )
        identity_sessions, oidc_login = _build_oidc_login(settings, sessions)
        app.state.identity_session_service = identity_sessions
        app.state.oidc_login_coordinator = oidc_login
        chat_repository = SqlAlchemyChatRepository(sessions)
        approval_repository = SqlAlchemyApprovalRepository(sessions)
        audit_repository = SqlAlchemyToolAuditRepository(sessions)
        knowledge_repository = SqlAlchemyKnowledgeRepository(sessions)
        authorization = LocalDevelopmentAuthorization()
        policy = ToolPolicy()
        ai_profiles = SqlAIProfileRepository(sessions)
        lm_studio = LMStudioAdapter()
        ai_secret_store = None
        llm_adapters: dict[str, LLMAdapter] = {"lm_studio": lm_studio}
        embedding_adapters: dict[str, EmbeddingAdapter] = {"lm_studio": lm_studio}
        if settings.credential_encryption_key is not None:
            ai_secret_store = SqlEncryptedAISecretStore(
                sessions,
                FernetCredentialCipher(settings.credential_encryption_key.get_secret_value()),
            )
            openai_adapter = OpenAICompatibleAdapter(ai_secret_store)
            claude_adapter = ClaudeAdapter(ai_secret_store)
            llm_adapters["openai"] = openai_adapter
            llm_adapters["claude"] = claude_adapter
            embedding_adapters["openai"] = openai_adapter
        ai_bank = AIBank(
            ai_profiles,
            llm_adapters,
            embedding_adapters,
        )
        app.state.ai_bank = ai_bank
        app.state.ai_secret_store = ai_secret_store

        lexical_search = LocalLexicalKnowledgeSearch(knowledge_repository)
        retrieval_metrics = RetrievalMetrics()
        knowledge_search: KnowledgeSearchPort = FallbackKnowledgeSearch(
            HybridKnowledgeSearch(knowledge_repository, ai_bank), lexical_search, retrieval_metrics
        )
        app.state.knowledge_retrieval_metrics = retrieval_metrics

        mcp_gateways: dict[str, ToolGateway] = {}
        if settings.mcp_enabled and settings.mcp_demo_enabled:
            mcp_gateways["demo"] = McpToolGateway(
                settings.mcp_demo_url,
                policy,
                settings.mcp_timeout_seconds,
                settings.mcp_max_result_characters,
                server_label="demo",
            )
        if settings.mcp_enabled and settings.mcp_jira_enabled:
            jira_auth = None
            if settings.mcp_jira_oauth_storage:
                jira_auth = OAuthClientProvider(
                    server_url=settings.mcp_jira_url,
                    client_metadata=OAuthClientMetadata(
                        client_name=settings.app_name,
                        redirect_uris=[AnyUrl("http://127.0.0.1:8765/callback")],
                        grant_types=["authorization_code", "refresh_token"],
                        response_types=["code"],
                    ),
                    storage=JsonOAuthTokenStorage(Path(settings.mcp_jira_oauth_storage)),
                )
            jira_headers = (
                {"Authorization": settings.mcp_jira_authorization.get_secret_value()}
                if settings.mcp_jira_authorization
                else None
            )
            mcp_gateways["jira"] = McpToolGateway(
                settings.mcp_jira_url,
                policy,
                settings.mcp_timeout_seconds,
                settings.mcp_max_result_characters,
                server_label="jira",
                headers=jira_headers,
                auth=jira_auth,
            )
        if settings.mcp_enabled and settings.mcp_slack_enabled:
            slack_auth = settings.mcp_slack_authorization
            if slack_auth is None:
                message = "Validated Slack MCP authorization disappeared."
                raise RuntimeError(message)
            mcp_gateways["slack"] = McpToolGateway(
                settings.mcp_slack_url,
                policy,
                settings.mcp_timeout_seconds,
                settings.mcp_max_result_characters,
                server_label="slack",
                headers={"Authorization": slack_auth.get_secret_value()},
            )
        integration_service: IntegrationConnectionService | None = None
        integration_oauth_service: OAuthFlowCoordinator | None = None
        effective_tool_access_reader: SqlEffectiveToolAccessReader | None = None
        tool_gateway: ToolGateway
        if settings.integration_connections_enabled:
            encryption_key = settings.credential_encryption_key
            if encryption_key is None:
                msg = "Validated credential encryption key disappeared."
                raise RuntimeError(msg)
            connection_repository = SqlAlchemyIntegrationConnectionRepository(sessions)
            effective_tool_access_reader = SqlEffectiveToolAccessReader(connection_repository)
            credential_cipher = FernetCredentialCipher(encryption_key.get_secret_value())
            gateway_factory = McpConnectionGatewayFactory(
                policy,
                settings.mcp_timeout_seconds,
                settings.mcp_max_result_characters,
            )
            credential_resolver = OAuthCredentialResolver(
                connection_repository,
                credential_cipher,
                settings.mcp_timeout_seconds,
            )
            tool_gateway = TenantMcpToolGateway(
                connection_repository,
                credential_cipher,
                gateway_factory,
                mcp_gateways,
                credential_resolver,
            )
            integration_service = IntegrationConnectionService(
                connection_repository,
                credential_cipher,
                gateway_factory,
                credential_resolver,
            )
            slack_client_id = (
                settings.slack_oauth_client_id.get_secret_value()
                if settings.slack_oauth_client_id
                else None
            )
            slack_client_secret = (
                settings.slack_oauth_client_secret.get_secret_value()
                if settings.slack_oauth_client_secret
                else None
            )
            integration_oauth_service = OAuthFlowCoordinator(
                integration_service,
                encryption_key.get_secret_value(),
                settings.oauth_public_api_base_url,
                settings.oauth_web_base_url,
                slack_client_id,
                slack_client_secret,
                settings.mcp_timeout_seconds,
            )
        else:
            tool_gateway = (
                CompositeMcpToolGateway(mcp_gateways) if mcp_gateways else DisabledToolGateway()
            )
        tool_call_metrics = ToolCallMetrics()
        tool_gateway = InstrumentedToolGateway(tool_gateway, tool_call_metrics)
        app.state.tool_call_metrics = tool_call_metrics
        app.state.effective_access_preview_service = EffectiveAccessPreviewService(
            app.state.identity_context_resolver,
            app.state.agent_catalog_service,
            effective_tool_access_reader,
            SqlAccessPreviewUnitReader(sessions),
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
        elif settings.model_provider is ModelProviderName.DETERMINISTIC:
            model_provider = DeterministicModelProvider()
        else:
            model_provider = ai_bank

        work_signer = WorkEnvelopeSigner(settings.work_envelope_signing_key.get_secret_value())
        job_service = JobService(
            SqlAlchemyJobRepository(sessions),
            RabbitJobPublisher(settings.rabbitmq_url.get_secret_value()),
            work_signer,
        )
        app.state.job_service = job_service
        object_storage_metrics = ObjectStorageMetrics()
        app.state.object_storage_metrics = object_storage_metrics
        object_storage = MinioObjectStorage(
            settings.minio_endpoint,
            settings.minio_access_key.get_secret_value(),
            settings.minio_secret_key.get_secret_value(),
            settings.minio_bucket,
            object_storage_metrics,
        )
        artifact_repository = SqlArtifactRepository(sessions)
        artifact_service = ArtifactService(
            artifact_repository,
            object_storage,
            ArtifactRendererRegistry(
                (
                    *(TextArtifactRenderer(artifact_type) for artifact_type in ArtifactType),
                    WordDocumentRenderer(),
                    PowerPointRenderer(),
                    ExcelWorkbookRenderer(),
                )
            ),
        )

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
                agent_authorizer=app.state.agent_catalog_service,
                context_resolver=app.state.identity_context_resolver,
                background_dispatcher=job_service,
                artifact_service=artifact_service,
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
            ingestion_queue_metrics = IngestionQueueMetrics()
            app.state.ingestion_queue_metrics = ingestion_queue_metrics
            app.state.knowledge_service = KnowledgeService(
                knowledge_repository,
                object_storage,
                RabbitMqIngestionPublisher(
                    settings.rabbitmq_url.get_secret_value(),
                    settings.ingestion_queue_name,
                    settings.ingestion_dead_letter_queue_name,
                    work_signer,
                    ingestion_queue_metrics,
                ),
                authorization,
                settings.max_upload_bytes,
            )
            app.state.artifact_service = artifact_service
            app.state.artifact_execution_service = ArtifactExecutionService(
                artifact_repository,
                artifact_service,
                (DryRunActionProvider(), McpActionProvider(artifact_repository, tool_gateway)),
            )
            app.state.integration_service = integration_service
            app.state.integration_oauth_service = integration_oauth_service
            try:
                yield
            finally:
                await supervisor.shutdown()
        await engine.dispose()

    return lifespan
