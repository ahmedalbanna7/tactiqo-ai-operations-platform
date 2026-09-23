"""Thin HTTP and SSE adapters for system and F1 application use cases."""

from __future__ import annotations

import asyncio
import hmac
import json
from typing import TYPE_CHECKING, Annotated, Literal, cast
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse

from tactiqo.agents.application.execution_classifier import OPERATIONAL_AGENT_CODES
from tactiqo.agents.catalog.application.administration import (
    AgentApprovalChainInput,
    AgentAssignmentInput,
    AgentCatalogAdministrationService,
)
from tactiqo.ai.application.bank import AIBank, ProviderUnavailableError
from tactiqo.ai.domain.models import ProviderHealth, ProviderKind, ProviderProfile, ProviderStatus
from tactiqo.artifacts.domain.models import ArtifactType, ReviewDecision
from tactiqo.authorization.application.preview import AccessPreviewScenario
from tactiqo.authorization.domain.models import (
    PolicyAction,
    PolicyEffect,
    PolicyObligation,
    PolicyObligationType,
)
from tactiqo.identity.application.administration import (
    AdministrationDeniedError,
    ChildUnitInput,
    DepartmentInput,
    MembershipInput,
    OrganizationAdministrationService,
)
from tactiqo.identity.application.lifecycle import (
    TenantLifecycleAction,
    TenantLifecycleService,
)
from tactiqo.identity.application.settings_navigation import CompanySettingsNavigation
from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.integrations.application.service import IntegrationAdministrationDeniedError
from tactiqo.integrations.domain.models import (
    ConnectionScope,
    IntegrationConnection,
    IntegrationProvider,
)
from tactiqo.integrations.infrastructure.oauth import OAuthFlowError
from tactiqo.knowledge.domain.models import KnowledgeDomain, KnowledgePurpose
from tactiqo.shared.domain.health import HealthStatus
from tactiqo.shared.infrastructure.settings import RuntimeEnvironment
from tactiqo.tools.domain.models import ApprovalStatus
from tactiqo_api.middleware import get_correlation_id
from tactiqo_api.schemas import (
    AccessPreviewScenarioRequest,
    ActionProviderMappingRequest,
    ActionProviderMappingResponse,
    AgentAssignmentDetailResponse,
    AgentAssignmentResponse,
    AgentCatalogItemResponse,
    AgentObligationResponse,
    AgentRunResponse,
    AICredentialRequest,
    AICredentialResponse,
    AIEmbeddingTestRequest,
    AIEmbeddingTestResponse,
    AIHealthResponse,
    AILLMTestRequest,
    AILLMTestResponse,
    AIProfileRequest,
    AIProfileResponse,
    ApprovalDecisionRequest,
    ApprovalResponse,
    ArtifactActionResponse,
    ArtifactLegalHoldRequest,
    ArtifactPolicyRequest,
    ArtifactPolicyResponse,
    ArtifactPurgeRequest,
    ArtifactPurgeResponse,
    ArtifactResponse,
    ArtifactRetentionResponse,
    ArtifactReviewDecisionRequest,
    ArtifactReviewResponse,
    ArtifactTemplateResponse,
    ArtifactUsageResponse,
    AssignMembershipRequest,
    AssignPrivilegedRoleRequest,
    ChatAttachmentResponse,
    CompanyPersonResponse,
    CompanyUnitResponse,
    ComponentHealthResponse,
    ConnectionToolGrantRequest,
    ConnectionToolGrantResponse,
    ConversationResponse,
    CreateAgentAssignmentRequest,
    CreateArtifactTemplateRequest,
    CreateConversationRequest,
    CreateDepartmentRequest,
    CreateExecutionDraftRequest,
    CreateIntegrationConnectionRequest,
    CreateOrganizationInvitationRequest,
    CreateProjectRequest,
    CreateReportDraftRequest,
    CreateTeamRequest,
    DepartmentResponse,
    DocumentResponse,
    EffectiveAccessPreviewResponse,
    EffectiveAgentCardResponse,
    ExecuteArtifactActionRequest,
    HealthResponse,
    InstallAgentRequest,
    IntegrationConnectionResponse,
    IntegrationVerificationResponse,
    InvitationAdminResponse,
    InvitationLoginResponse,
    InvitationPreviewResponse,
    InvitationTokenRequest,
    JobMetricsResponse,
    JobResponse,
    MessageResponse,
    OrganizationInvitationResponse,
    ReconnectIntegrationRequest,
    RevokeDocumentRequest,
    RoleHistoryResponse,
    SendMessageRequest,
    ServiceInfoResponse,
    SessionResponse,
    SetAgentApprovalChainRequest,
    SetAgentEnabledRequest,
    SetMemberStatusRequest,
    SettingsSectionResponse,
    SourcePreviewItemResponse,
    StartIntegrationOAuthRequest,
    StartIntegrationOAuthResponse,
    TenantLifecycleRequestBody,
    TenantLifecycleResponse,
    ValidateArtifactActionRequest,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tactiqo.agents.catalog.application.service import AgentCatalogService
    from tactiqo.agents.catalog.domain.models import EffectiveAgentCard
    from tactiqo.ai.application.ports import AISecretStore
    from tactiqo.artifacts.application.execution import ArtifactExecutionService
    from tactiqo.artifacts.application.service import ArtifactService
    from tactiqo.artifacts.domain.models import (
        Artifact,
        ArtifactActionRun,
        ArtifactReview,
        ArtifactTemplate,
        OrganizationArtifactPolicy,
    )
    from tactiqo.authorization.application.preview import EffectiveAccessPreviewService
    from tactiqo.chat.application.service import ChatService
    from tactiqo.chat.domain.models import AgentRun, Conversation, Message
    from tactiqo.identity.application.context import ExecutionContextResolver
    from tactiqo.identity.application.invitations import OrganizationInvitationService
    from tactiqo.identity.infrastructure.sessions import OidcLoginCoordinator, SqlSessionService
    from tactiqo.integrations.application.service import IntegrationConnectionService
    from tactiqo.integrations.domain.models import ConnectionToolGrant
    from tactiqo.integrations.infrastructure.oauth import OAuthFlowCoordinator
    from tactiqo.jobs.application.service import JobService
    from tactiqo.jobs.domain.models import Job
    from tactiqo.knowledge.application.service import KnowledgeService
    from tactiqo.knowledge.domain.models import KnowledgeDocument
    from tactiqo.shared.application.health import ReadinessService
    from tactiqo.shared.domain.execution import ExecutionContext
    from tactiqo.shared.infrastructure.settings import Settings
    from tactiqo.tools.application.service import ApprovalService
    from tactiqo.tools.domain.models import ApprovalRequest

router = APIRouter(tags=["system"])
api_router = APIRouter(prefix="/api/v1")


def _settings(request: Request) -> Settings:
    return cast("Settings", request.app.state.settings)


async def _context(request: Request) -> ExecutionContext:
    settings = _settings(request)
    correlation_id = get_correlation_id() or str(uuid4())
    if settings.local_development_context_enabled:
        resolver = cast("ExecutionContextResolver", request.app.state.identity_context_resolver)
        context = await resolver.resolve_delegated(
            settings.local_actor_id,
            settings.local_organization_id,
            correlation_id,
            "step_up",
        )
        if context is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
        return context
    opaque_session = request.cookies.get(settings.oidc_session_cookie_name)
    if not opaque_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    resolver = cast("ExecutionContextResolver", request.app.state.identity_context_resolver)
    context = await resolver.resolve(opaque_session, correlation_id)
    if context is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    return context


def _chat(request: Request) -> ChatService:
    return cast("ChatService", request.app.state.chat_service)


def _approvals(request: Request) -> ApprovalService:
    return cast("ApprovalService", request.app.state.approval_service)


def _knowledge(request: Request) -> KnowledgeService:
    return cast("KnowledgeService", request.app.state.knowledge_service)


def _artifacts(request: Request) -> ArtifactService:
    return cast("ArtifactService", request.app.state.artifact_service)


def _artifact_execution(request: Request) -> ArtifactExecutionService:
    return cast("ArtifactExecutionService", request.app.state.artifact_execution_service)


def _jobs(request: Request) -> JobService:
    return cast("JobService", request.app.state.job_service)


def _integrations(request: Request) -> IntegrationConnectionService:
    service = request.app.state.integration_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Integrations are disabled.")
    return cast("IntegrationConnectionService", service)


def _integration_oauth(request: Request) -> OAuthFlowCoordinator:
    service = request.app.state.integration_oauth_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Integration OAuth is disabled.")
    return cast("OAuthFlowCoordinator", service)


def _identity_sessions(request: Request) -> SqlSessionService:
    return cast("SqlSessionService", request.app.state.identity_session_service)


def _oidc_login(request: Request) -> OidcLoginCoordinator:
    coordinator = request.app.state.oidc_login_coordinator
    if coordinator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OIDC login is disabled.")
    return cast("OidcLoginCoordinator", coordinator)


def _organization_admin(request: Request) -> OrganizationAdministrationService:
    return cast(
        "OrganizationAdministrationService",
        request.app.state.organization_administration_service,
    )


def _organization_invitations(request: Request) -> OrganizationInvitationService:
    return cast(
        "OrganizationInvitationService", request.app.state.organization_invitation_service
    )


def _agent_catalog(request: Request) -> AgentCatalogService:
    return cast("AgentCatalogService", request.app.state.agent_catalog_service)


def _agent_catalog_admin(request: Request) -> AgentCatalogAdministrationService:
    return cast(
        "AgentCatalogAdministrationService",
        request.app.state.agent_catalog_administration_service,
    )


def _ai_bank(request: Request) -> AIBank:
    return cast("AIBank", request.app.state.ai_bank)


def _ai_secrets(request: Request) -> AISecretStore | None:
    return cast("AISecretStore | None", request.app.state.ai_secret_store)


def _ai_profile_response(profile: ProviderProfile) -> AIProfileResponse:
    return AIProfileResponse(
        name=profile.name,
        kind=profile.kind.value,
        provider=profile.provider,
        model=profile.model,
        endpoint=profile.endpoint,
        status=profile.status.value,
        version=profile.version,
        has_secret_reference=bool(profile.secret_reference),
        capabilities=profile.capabilities,
        routing_priority=profile.routing_priority,
        allowed_classifications=profile.allowed_classifications,
    )


@api_router.get("/ai/profiles")
async def list_ai_profiles(request: Request) -> list[AIProfileResponse]:
    """Return Owner-visible non-secret AI profiles."""
    try:
        profiles = await _ai_bank(request).profiles(await _context(request))
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    return [_ai_profile_response(profile) for profile in profiles]


@api_router.post("/ai/credentials", status_code=status.HTTP_201_CREATED)
async def create_ai_credential(
    payload: AICredentialRequest, request: Request
) -> AICredentialResponse:
    """Encrypt one Owner-supplied API key and return only an opaque reference."""
    context = await _context(request)
    _ai_bank(request).require_admin(context)
    store = _ai_secrets(request)
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Encrypted AI credential storage is not configured.",
        )
    reference = await store.put(
        context.organization_id,
        payload.provider,
        payload.api_key.get_secret_value(),
        context.actor_id,
    )
    return AICredentialResponse(provider=payload.provider, secret_reference=reference)


@api_router.post("/ai/profiles/test")
async def test_ai_profile(payload: AIProfileRequest, request: Request) -> AIHealthResponse:
    """Discover LM Studio models without changing active configuration."""
    context = await _context(request)
    _ai_bank(request).require_admin(context)
    profile = _ai_profile(payload)
    health = await _ai_bank(request).test(profile)
    return _ai_health_response(health)


@api_router.put("/ai/profiles/{profile_name}")
async def configure_ai_profile(
    profile_name: str, payload: AIProfileRequest, request: Request
) -> AIHealthResponse:
    """Validate then activate an AI profile atomically."""
    if profile_name != payload.name:
        raise HTTPException(status.HTTP_409_CONFLICT, "Profile name mismatch.")
    context = await _context(request)
    if payload.provider in {"openai", "claude"} and payload.secret_reference:
        store = _ai_secrets(request)
        if store is None or not await store.belongs_to(
            payload.secret_reference, context.organization_id, payload.provider
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Credential reference denied.")
    health = await _ai_bank(request).configure(context, _ai_profile(payload))
    if not health.healthy or payload.model not in health.models:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provider or model unavailable.")
    return _ai_health_response(health)


@api_router.post("/ai/profiles/{profile_name}/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_ai_profile(profile_name: str, request: Request) -> None:
    """Remove one provider from live routing without deleting its configuration."""
    context = await _context(request)
    if not await _ai_bank(request).disable(context, profile_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider profile not found.")


@api_router.post("/ai/test/llm")
async def test_active_llm(payload: AILLMTestRequest, request: Request) -> AILLMTestResponse:
    """Run the active LLM through the same bank used by LangGraph."""
    context = await _context(request)
    _ai_bank(request).require_admin(context)
    try:
        turn = await _ai_bank(request).plan(payload.prompt, (), (), context)
    except ProviderUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    return AILLMTestResponse(text=turn.text)


@api_router.post("/ai/test/embedding")
async def test_active_embedding(
    payload: AIEmbeddingTestRequest, request: Request
) -> AIEmbeddingTestResponse:
    """Generate diagnostics from the active multilingual embedding profile."""
    context = await _context(request)
    _ai_bank(request).require_admin(context)
    try:
        result = await _ai_bank(request).embed((payload.text,), context)
    except ProviderUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    return AIEmbeddingTestResponse(
        model=result.model,
        embedding_space_id=result.embedding_space_id,
        dimensions=result.dimensions,
        preview=result.vectors[0][:8],
    )


def _ai_profile(payload: AIProfileRequest) -> ProviderProfile:
    return ProviderProfile(
        name=payload.name,
        provider=payload.provider,
        kind=ProviderKind(payload.kind),
        model=payload.model,
        endpoint=payload.endpoint,
        status=ProviderStatus.ENABLED,
        secret_reference=payload.secret_reference,
        timeout_seconds=payload.timeout_seconds,
        maximum_retries=payload.maximum_retries,
        maximum_concurrency=payload.maximum_concurrency,
        daily_unit_limit=payload.daily_unit_limit,
        capabilities=payload.capabilities,
        routing_priority=payload.routing_priority,
        allowed_classifications=payload.allowed_classifications or (
            ("public", "internal", "confidential", "restricted")
            if payload.provider == "lm_studio"
            else ("public", "internal")
        ),
    )


def _ai_health_response(health: ProviderHealth) -> AIHealthResponse:
    return AIHealthResponse(
        healthy=health.healthy,
        latency_ms=health.latency_ms,
        models=health.models,
        error_code=health.error_code,
    )


def _agent_card_response(card: EffectiveAgentCard) -> EffectiveAgentCardResponse:
    return EffectiveAgentCardResponse(
        code=card.code,
        name=card.name,
        description=card.description,
        category=card.category.value,
        version=card.version,
        capabilities=card.capabilities,
        allowed_actions=tuple(action.value for action in card.allowed_actions),
        obligations=tuple(
            AgentObligationResponse(kind=item.kind.value, value=item.value)
            for item in card.obligations
        ),
    )


@api_router.get("/agents")
async def list_effective_agents(request: Request) -> list[EffectiveAgentCardResponse]:
    """Return only server-compiled visible agents with implemented routes."""
    cards = await _agent_catalog(request).effective_cards(await _context(request))
    return [
        _agent_card_response(card)
        for card in cards
        if card.code in OPERATIONAL_AGENT_CODES
    ]


@api_router.get("/company/settings/navigation")
async def company_settings_navigation(request: Request) -> list[SettingsSectionResponse]:
    """Return only server-authorized settings destinations."""
    sections = CompanySettingsNavigation.sections(await _context(request))
    return [SettingsSectionResponse(code=item.code, label=item.label) for item in sections]


@api_router.get("/agents/{agent_code}")
async def get_effective_agent(agent_code: str, request: Request) -> EffectiveAgentCardResponse:
    """Re-evaluate direct agent use and hide denied or missing agents equally."""
    if agent_code not in OPERATIONAL_AGENT_CODES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found.")
    card = await _agent_catalog(request).authorize_invocation(
        await _context(request), agent_code, PolicyAction.USE
    )
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found.")
    return _agent_card_response(card)


@api_router.post("/agent-catalog/install", status_code=status.HTTP_204_NO_CONTENT)
async def install_agent(payload: InstallAgentRequest, request: Request) -> None:
    """Install an immutable version disabled by default."""
    try:
        await _agent_catalog_admin(request).install(
            await _context(request), payload.agent_code, payload.version
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent version not found.") from error


@api_router.get("/agent-catalog/catalog", response_model=list[AgentCatalogItemResponse])
async def list_agent_catalog(request: Request) -> list[AgentCatalogItemResponse]:
    """List non-secret agent definitions, versions and tenant install status."""
    try:
        items = await _agent_catalog_admin(request).list_catalog(await _context(request))
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    return [AgentCatalogItemResponse(
        code=item.code,
        name=item.name,
        description=item.description,
        category=item.category,
        selected_version=item.selected_version,
        versions=item.versions,
        installed=item.installed,
        enabled=item.enabled,
    ) for item in items]


@api_router.patch("/agent-catalog/{agent_code}", status_code=status.HTTP_204_NO_CONTENT)
async def set_agent_enabled(
    agent_code: str,
    payload: SetAgentEnabledRequest,
    request: Request,
) -> None:
    """Enable or disable one installed agent."""
    try:
        changed = await _agent_catalog_admin(request).set_enabled(
            await _context(request), agent_code, enabled=payload.enabled
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found.")


@api_router.post("/agent-catalog/assignments", status_code=status.HTTP_201_CREATED)
async def create_agent_assignment(
    payload: CreateAgentAssignmentRequest,
    request: Request,
) -> AgentAssignmentResponse:
    """Create independent grants, scopes, tools, quotas, and obligations."""
    try:
        assignment_id = await _agent_catalog_admin(request).assign(
            await _context(request),
            AgentAssignmentInput(
                agent_code=payload.agent_code,
                target_type=payload.target_type,
                target_id=payload.target_id,
                actions=tuple(PolicyAction(value) for value in payload.actions),
                effect=PolicyEffect(payload.effect),
                classification_ceiling=payload.classification_ceiling,
                data_domains=payload.data_domains,
                connection_ids=payload.connection_ids,
                tool_names=payload.tool_names,
                quota=payload.quota,
                budget=payload.budget,
                obligations=tuple(
                    PolicyObligation(PolicyObligationType(item.kind), item.value)
                    for item in payload.obligations
                ),
            ),
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except (ValueError, KeyError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found.") from error
    return AgentAssignmentResponse(id=assignment_id)


@api_router.get("/agent-catalog/assignments")
async def list_agent_assignments(request: Request) -> list[AgentAssignmentDetailResponse]:
    """List bounded assignment metadata for the current tenant's administrators."""
    try:
        rows = await _agent_catalog_admin(request).list_assignments(await _context(request))
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    return [
        AgentAssignmentDetailResponse(
            id=row.id,
            agent_code=row.agent_code,
            target_type=row.target_type,
            target_id=row.target_id,
            actions=row.actions,
            effect=row.effect,
            classification_ceiling=row.classification_ceiling,
            active=row.active,
        )
        for row in rows
    ]


@api_router.delete(
    "/agent-catalog/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_agent_assignment(assignment_id: UUID, request: Request) -> None:
    """Immediately revoke one tenant assignment."""
    try:
        changed = await _agent_catalog_admin(request).revoke_assignment(
            await _context(request), assignment_id
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")


@api_router.put(
    "/agent-catalog/approval-chains",
    status_code=status.HTTP_201_CREATED,
)
async def set_agent_approval_chain(
    payload: SetAgentApprovalChainRequest, request: Request
) -> AgentAssignmentResponse:
    """Create or replace an approval-chain selector without exposing policy internals."""
    try:
        chain_id = await _agent_catalog_admin(request).set_approval_chain(
            await _context(request),
            AgentApprovalChainInput(
                agent_code=payload.agent_code,
                action=PolicyAction(payload.action),
                risk=payload.risk,
                target_system=payload.target_system,
                approver_steps=payload.approver_steps,
            ),
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Installed agent not found.") from error
    return AgentAssignmentResponse(id=chain_id)


def _tenant_lifecycle(request: Request) -> TenantLifecycleService:
    return cast("TenantLifecycleService", request.app.state.tenant_lifecycle_service)


@api_router.post("/company/departments", status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: CreateDepartmentRequest, request: Request
) -> DepartmentResponse:
    """Create a tenant department using server-derived Owner/Admin authority."""
    try:
        row = await _organization_admin(request).create_department(
            await _context(request),
            DepartmentInput(
                payload.code,
                payload.name,
                payload.classification_ceiling,
                payload.manager_user_id,
            ),
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.") from error
    return DepartmentResponse(id=row.id, code=row.code, name=row.name)


@api_router.get("/company/units")
async def list_company_units(request: Request) -> list[CompanyUnitResponse]:
    """List tenant structure only for Owner/Organization Admin."""
    try:
        units = await _organization_admin(request).list_units(await _context(request))
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    return [
        CompanyUnitResponse(
            id=item.id,
            kind=item.kind,
            code=item.code,
            name=item.name,
            department_id=item.department_id,
            manager_user_id=item.manager_user_id,
            classification_ceiling=item.classification_ceiling,
            status=item.status,
        )
        for item in units
    ]


@api_router.get("/company/people")
async def list_company_people(request: Request) -> list[CompanyPersonResponse]:
    """Return a bounded tenant people directory only to administrators."""
    try:
        people = await _organization_admin(request).list_people(await _context(request))
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    return [
        CompanyPersonResponse(
            user_id=item.user_id,
            display_name=item.display_name,
            email=item.email,
            status=item.status,
            classification_clearance=item.classification_clearance,
            role_codes=item.role_codes,
        )
        for item in people
    ]


@api_router.put("/company/people/{user_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def set_company_member_status(
    user_id: UUID, payload: SetMemberStatusRequest, request: Request
) -> None:
    """Owner-only, step-up protected suspension or reactivation."""
    try:
        changed = await _organization_admin(request).set_member_status(
            await _context(request), user_id, payload.status
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The final active Owner cannot be suspended.",
        ) from error
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.")


@api_router.get("/company/people/{user_id}/roles", response_model=list[RoleHistoryResponse])
async def list_company_member_roles(user_id: UUID, request: Request) -> list[RoleHistoryResponse]:
    """Show a bounded role audit history for a tenant member."""
    try:
        rows = await _organization_admin(request).list_role_history(
            await _context(request), user_id
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.")
    return [RoleHistoryResponse(**row) for row in rows]


@api_router.delete("/company/roles/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_company_role(assignment_id: UUID, request: Request) -> None:
    """Owner-only, step-up protected revocation with last-Owner protection."""
    try:
        revoked = await _organization_admin(request).revoke_role(
            await _context(request), assignment_id
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The final active Owner cannot be removed.",
        ) from error
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role assignment not found.")


@api_router.post(
    "/company/people/{user_id}/access-preview",
    response_model=EffectiveAccessPreviewResponse,
)
async def preview_company_member_access(
    user_id: UUID, payload: AccessPreviewScenarioRequest, request: Request
) -> EffectiveAccessPreviewResponse:
    """Preview current/simulated role-derived agent access without writes or impersonation."""
    service = cast(
        "EffectiveAccessPreviewService", request.app.state.effective_access_preview_service
    )
    try:
        result = await service.preview(
            await _context(request),
            user_id,
            AccessPreviewScenario(
                role_code=payload.role_code,
                role_operation=payload.operation,
                scope_kind=payload.scope_kind,
                scope_id=str(payload.scope_id) if payload.scope_id else None,
                scope_operation=payload.scope_operation,
            ),
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not available.") from error
    except ValueError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid access preview scenario.",
        ) from error
    return EffectiveAccessPreviewResponse(
        user_id=result.user_id,
        organization_id=result.organization_id,
        policy_version=result.policy_version,
        evaluated_at=result.evaluated_at,
        scope=result.scope,
        agents=tuple(
            {
                "code": agent.code,
                "name": agent.name,
                "category": agent.category,
                "allowed_actions": agent.allowed_actions,
                "reason_code": "allowed",
            }
            for agent in result.agents
        ),
        proposed_role=result.proposed_role,
        role_operation=result.role_operation,
        proposed_agents=tuple(
            {
                "code": agent.code,
                "name": agent.name,
                "category": agent.category,
                "allowed_actions": agent.allowed_actions,
                "reason_code": "allowed",
            }
            for agent in result.proposed_agents
        ),
        gained_agents=result.gained_agents,
        lost_agents=result.lost_agents,
        action_changes=tuple(
            {
                "code": change.code,
                "name": change.name,
                "gained_actions": change.gained_actions,
                "lost_actions": change.lost_actions,
            }
            for change in result.action_changes
        ),
        tool_grants=tuple(
            {
                "provider": grant.provider,
                "connection_name": grant.connection_name,
                "tool_name": grant.tool_name,
                "permission": grant.permission,
            }
            for grant in result.tool_grants
        ),
        tools_truncated=result.tools_truncated,
        proposed_scope_kind=result.proposed_scope_kind,
        proposed_scope_id=(
            UUID(result.proposed_scope_id) if result.proposed_scope_id is not None else None
        ),
        scope_operation=result.scope_operation,
    )


@api_router.get("/company/invitations")
async def list_company_invitations(request: Request) -> list[InvitationAdminResponse]:
    """List only non-secret invitation status for the caller's organization."""
    try:
        invitations = await _organization_invitations(request).list(await _context(request))
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    return [
        InvitationAdminResponse(
            id=item.id,
            department_id=item.department_id,
            department_name=item.department_name,
            status=item.status,
            expires_at=item.expires_at,
        )
        for item in invitations
    ]


@api_router.post("/company/invitations", status_code=status.HTTP_201_CREATED)
async def create_company_invitation(
    payload: CreateOrganizationInvitationRequest, request: Request
) -> OrganizationInvitationResponse:
    """Create a 72-hour, single-use tenant invitation and reveal its link once."""
    try:
        invitation = await _organization_invitations(request).create(
            await _context(request), payload.department_id
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found.") from error
    settings = _settings(request)
    link = f"{settings.oauth_web_base_url.rstrip('/')}/#invite={invitation.token}"
    return OrganizationInvitationResponse(
        id=invitation.invitation_id,
        department_id=invitation.department_id,
        link=link,
        expires_at=invitation.expires_at,
    )


@api_router.delete("/company/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_company_invitation(invitation_id: UUID, request: Request) -> None:
    """Revoke a pending invitation inside the current tenant."""
    try:
        revoked = await _organization_invitations(request).revoke(
            await _context(request), invitation_id
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found.")


@api_router.post("/company/teams", status_code=status.HTTP_201_CREATED)
async def create_team(payload: CreateTeamRequest, request: Request) -> DepartmentResponse:
    """Create a team under a tenant-owned department."""
    try:
        row = await _organization_admin(request).create_team(
            await _context(request),
            ChildUnitInput(
                payload.department_id, payload.name, manager_user_id=payload.manager_user_id
            ),
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department or member not found.") from error
    return DepartmentResponse(id=row.id, code=row.code, name=row.name)


@api_router.post("/company/projects", status_code=status.HTTP_201_CREATED)
async def create_project(payload: CreateProjectRequest, request: Request) -> DepartmentResponse:
    """Create a project under a tenant-owned department."""
    try:
        row = await _organization_admin(request).create_project(
            await _context(request),
            ChildUnitInput(
                payload.department_id,
                payload.name,
                code=payload.code,
                manager_user_id=payload.manager_user_id,
            ),
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department or member not found.") from error
    return DepartmentResponse(id=row.id, code=row.code, name=row.name)


@api_router.post("/company/roles", status_code=status.HTTP_204_NO_CONTENT)
async def assign_privileged_role(payload: AssignPrivilegedRoleRequest, request: Request) -> None:
    """Assign an Owner-controlled organization privilege with step-up assurance."""
    try:
        await _organization_admin(request).assign_privileged_role(
            await _context(request), payload.user_id, OrganizationRole(payload.role)
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.") from error


@api_router.post(
    "/company/{kind}/{unit_id}/members",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def assign_unit_membership(
    kind: str,
    unit_id: UUID,
    payload: AssignMembershipRequest,
    request: Request,
) -> None:
    """Assign a member using tenant-safe department/team/project invariants."""
    try:
        await _organization_admin(request).assign_membership(
            await _context(request),
            kind,
            MembershipInput(unit_id, payload.user_id),
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unit or member not found.") from error


@api_router.post(
    "/company/lifecycle/requests",
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_tenant_lifecycle(
    payload: TenantLifecycleRequestBody,
    request: Request,
) -> TenantLifecycleResponse:
    """Create a durable request that cannot be approved by its initiator."""
    try:
        row = await _tenant_lifecycle(request).request(
            await _context(request),
            TenantLifecycleAction(payload.action),
            payload.target_user_id,
            payload.retention_days,
        )
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found.") from error
    return TenantLifecycleResponse(id=row.id, action=row.action, status=row.status)


@api_router.post("/company/lifecycle/requests/{request_id}/approve")
async def approve_tenant_lifecycle(
    request_id: UUID,
    request: Request,
) -> TenantLifecycleResponse:
    """Apply a tenant lifecycle request using a different step-up administrator."""
    try:
        row = await _tenant_lifecycle(request).approve(await _context(request), request_id)
    except AdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approval conflict.") from error
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    return TenantLifecycleResponse(id=row.id, action=row.action, status=row.status)


@api_router.get("/auth/login")
async def oidc_login(request: Request, organization_id: str) -> RedirectResponse:
    """Begin OIDC Authorization Code + PKCE for one requested tenant."""
    return RedirectResponse(_oidc_login(request).start(organization_id))


@api_router.post("/auth/invitations/preview")
async def inspect_invitation(
    payload: InvitationTokenRequest, request: Request
) -> InvitationPreviewResponse:
    """Expose only the organization and department attached to a valid link."""
    invitation = await _organization_invitations(request).inspect(payload.token)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found or expired.")
    return InvitationPreviewResponse(
        organization_name=invitation.organization_name,
        department_id=invitation.department_id,
        department_name=invitation.department_name,
        expires_at=invitation.expires_at,
    )


@api_router.post("/auth/invitations/login")
async def accept_invitation_login(
    payload: InvitationTokenRequest, request: Request
) -> InvitationLoginResponse:
    """Start OIDC with encrypted, tenant-bound invitation state."""
    invitation = await _organization_invitations(request).inspect(payload.token)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found or expired.")
    return InvitationLoginResponse(
        authorization_url=_oidc_login(request).start(invitation.organization_id, payload.token)
    )


@api_router.get("/auth/callback")
async def oidc_callback(request: Request, code: str, state: str) -> RedirectResponse:
    """Exchange a provider code and set only an opaque application cookie."""
    settings = _settings(request)
    try:
        issued = await _oidc_login(request).callback(
            code,
            state,
            request.headers.get("user-agent", "unknown"),
            get_correlation_id() or str(uuid4()),
        )
    except Exception as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication failed.") from error
    response = RedirectResponse(settings.oauth_web_base_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        settings.oidc_session_cookie_name,
        issued.token,
        httponly=True,
        secure=settings.environment.value != "local",
        samesite="lax",
        max_age=settings.oidc_session_ttl_seconds,
        path="/",
    )
    return response


@api_router.get("/auth/sessions")
async def list_auth_sessions(request: Request) -> list[SessionResponse]:
    """List the current user's active sessions without token material."""
    context = await _context(request)
    if not context.session_id:
        return []
    rows = await _identity_sessions(request).list(
        UUID(context.actor_id), context.organization_id, UUID(context.session_id)
    )
    return [
        SessionResponse(
            id=row.id,
            assurance=row.assurance,
            created_at=row.created_at,
            expires_at=row.expires_at,
            current=row.current,
        )
        for row in rows
    ]


@api_router.post("/auth/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def refresh_auth_session(request: Request, response: Response) -> None:
    """Rotate the opaque cookie and invalidate the previous value immediately."""
    context = await _context(request)
    if not context.session_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    settings = _settings(request)
    issued = await _identity_sessions(request).refresh(
        UUID(context.actor_id),
        context.organization_id,
        UUID(context.session_id),
        context.correlation_id,
    )
    if issued is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    response.set_cookie(
        settings.oidc_session_cookie_name,
        issued.token,
        httponly=True,
        secure=settings.environment.value != "local",
        samesite="lax",
        max_age=settings.oidc_session_ttl_seconds,
        path="/",
    )


@api_router.delete("/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_auth_session(session_id: UUID, request: Request, response: Response) -> None:
    """Revoke one caller-owned session; foreign IDs return the same not-found result."""
    context = await _context(request)
    removed = await _identity_sessions(request).revoke(
        UUID(context.actor_id), context.organization_id, session_id, context.correlation_id
    )
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if context.session_id == str(session_id):
        response.delete_cookie(_settings(request).oidc_session_cookie_name, path="/")


@api_router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    """Revoke the current session and clear its cookie."""
    context = await _context(request)
    if context.session_id:
        await _identity_sessions(request).revoke(
            UUID(context.actor_id),
            context.organization_id,
            UUID(context.session_id),
            context.correlation_id,
        )
    response.delete_cookie(_settings(request).oidc_session_cookie_name, path="/")


@router.get("/")
async def service_info(request: Request) -> ServiceInfoResponse:
    """Return public service identity metadata."""
    settings = _settings(request)
    return ServiceInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get("/health/live")
async def liveness(request: Request) -> HealthResponse:
    """Return process liveness without dependency checks."""
    settings = _settings(request)
    return HealthResponse(
        status=HealthStatus.HEALTHY.value,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get("/internal/metrics", include_in_schema=False)
async def internal_metrics(request: Request) -> PlainTextResponse:
    """Expose low-cardinality process metrics only in local mode or with a scrape token."""
    settings = _settings(request)
    configured_token = settings.effective_metrics_auth_token
    if configured_token is not None:
        expected = f"Bearer {configured_token.get_secret_value()}"
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(
            supplied.encode("utf-8", errors="replace"), expected.encode("utf-8")
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    elif settings.metrics_auth_token_file is not None or settings.environment not in {
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
        RuntimeEnvironment.TEST,
    }:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")

    metrics = request.app.state.http_request_metrics
    rendered_metrics = metrics.render_prometheus()
    ai_bank = getattr(request.app.state, "ai_bank", None)
    if ai_bank is not None:
        rendered_metrics += ai_bank.render_metrics()
    tool_call_metrics = getattr(request.app.state, "tool_call_metrics", None)
    if tool_call_metrics is not None:
        rendered_metrics += tool_call_metrics.render_prometheus()
    retrieval_metrics = getattr(request.app.state, "knowledge_retrieval_metrics", None)
    if retrieval_metrics is not None:
        rendered_metrics += retrieval_metrics.render_prometheus()
    ingestion_queue_metrics = getattr(request.app.state, "ingestion_queue_metrics", None)
    if ingestion_queue_metrics is not None:
        rendered_metrics += ingestion_queue_metrics.render_prometheus()
    object_storage_metrics = getattr(request.app.state, "object_storage_metrics", None)
    if object_storage_metrics is not None:
        rendered_metrics += object_storage_metrics.render_prometheus()
    return PlainTextResponse(
        rendered_metrics,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get(
    "/health/ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def readiness(request: Request, response: Response) -> HealthResponse:
    """Return fail-closed dependency readiness."""
    settings = _settings(request)
    service: ReadinessService = request.app.state.readiness_service
    health = await service.evaluate()
    if health.status is HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=health.status.value,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        components=[
            ComponentHealthResponse(
                name=component.name,
                status=component.status.value,
                detail=component.detail,
            )
            for component in health.components
        ],
    )


@api_router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: CreateConversationRequest,
    request: Request,
) -> ConversationResponse:
    """Create a conversation in the local execution scope."""
    conversation = await _chat(request).create_conversation(await _context(request), payload.title)
    return _conversation_response(conversation)


@api_router.get("/conversations")
async def list_conversations(request: Request) -> list[ConversationResponse]:
    """List visible conversations newest first."""
    conversations = await _chat(request).list_conversations(await _context(request))
    return [_conversation_response(item) for item in conversations]


@api_router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: UUID, request: Request) -> list[MessageResponse]:
    """List ordered messages for a visible conversation."""
    messages = await _chat(request).list_messages(await _context(request), conversation_id)
    if messages is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return [_message_response(item) for item in messages]


@api_router.get("/conversations/{conversation_id}/attachments")
async def list_chat_attachments(
    conversation_id: UUID, request: Request
) -> list[ChatAttachmentResponse]:
    """List re-authorized knowledge attachments rendered inside chat."""
    items = await _chat(request).list_attachments(await _context(request), conversation_id)
    if items is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return [
        ChatAttachmentResponse(
            id=item.id,
            conversation_id=item.conversation_id,
            document_id=item.document_id,
            name=item.name,
            status=item.status,
            domain=item.domain,
            purpose=item.purpose,
            created_at=item.created_at,
        )
        for item in items
    ]


@api_router.post(
    "/conversations/{conversation_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    request: Request,
) -> AgentRunResponse:
    """Persist a user turn and start a bounded run."""
    run = await _chat(request).send_message(
        await _context(request),
        conversation_id,
        payload.content,
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return _run_response(run)


@api_router.get("/runs/{run_id}")
async def get_run(run_id: UUID, request: Request) -> AgentRunResponse:
    """Return current state for a visible run."""
    run = await _chat(request).get_run(await _context(request), run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return _run_response(run)


@api_router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: UUID, request: Request) -> AgentRunResponse:
    """Request cancellation of a visible run."""
    run = await _chat(request).cancel(await _context(request), run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return _run_response(run)


@api_router.get("/runs/{run_id}/events")
async def stream_events(run_id: UUID, request: Request, after: int = 0) -> StreamingResponse:
    """Stream ordered resumable events until the run becomes terminal."""
    context = await _context(request)
    if await _chat(request).get_run(context, run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")

    async def events() -> AsyncIterator[str]:
        cursor = after
        while True:
            batch = await _chat(request).list_events(context, run_id, cursor)
            if batch is None:
                return
            for event in batch:
                cursor = event.sequence
                data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {event.sequence}\nevent: {event.event_type.value}\ndata: {data}\n\n"
            run = await _chat(request).get_run(context, run_id)
            if run is None or (run.status.terminal and not batch):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(_settings(request).agent_event_poll_seconds)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_router.get("/jobs")
async def list_jobs(request: Request) -> list[JobResponse]:
    """List durable background jobs visible to the current actor."""
    items = await _jobs(request).list(await _context(request))
    return [_job_response(item) for item in items]


@api_router.get("/jobs-metrics")
async def job_metrics(request: Request) -> JobMetricsResponse:
    """Return background workload counters visible to the current actor."""
    return JobMetricsResponse(counts=await _jobs(request).metrics(await _context(request)))


@api_router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, request: Request) -> JobResponse:
    """Return progress for one visible background job."""
    item = await _jobs(request).get(job_id, await _context(request))
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return _job_response(item)


@api_router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: UUID, request: Request) -> JobResponse:
    """Request cooperative cancellation of one visible background job."""
    item = await _jobs(request).cancel(job_id, await _context(request))
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return _job_response(item)


@api_router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: UUID, request: Request) -> JobResponse:
    """Explicitly retry visible failed or dead-letter work."""
    try:
        item = await _jobs(request).retry(job_id, await _context(request))
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return _job_response(item)


@api_router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    request: Request,
) -> ApprovalResponse:
    """Record a scoped immutable human approval decision."""
    approval = await _approvals(request).decide(
        approval_id,
        ApprovalStatus(payload.decision),
        await _context(request),
    )
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found.")
    return _approval_response(approval)


@api_router.post(
    "/knowledge/documents",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(  # noqa: PLR0913 - explicit multipart contract
    request: Request,
    file: Annotated[UploadFile, File()],
    project_id: Annotated[str | None, Form()] = None,
    domain: Annotated[str, Form()] = "general",
    purpose: Annotated[str, Form()] = "research",
    conversation_id: Annotated[UUID | None, Form()] = None,
    owner_scope: Annotated[Literal["personal", "organization"], Form()] = "personal",
) -> DocumentResponse:
    """Store an original document and enqueue asynchronous parsing."""
    context = await _context(request)
    if conversation_id is not None and not await _chat(request).conversation_exists(
        context, conversation_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    if conversation_id is not None and owner_scope != "personal":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Chat attachments must remain personal."
        )
    settings = _settings(request)
    content = await file.read(settings.max_upload_bytes + 1)
    try:
        document = await _knowledge(request).upload(
            name=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            project_id=project_id,
            domain=KnowledgeDomain(domain),
            purpose=KnowledgePurpose(purpose),
            context=context,
            owner_scope=owner_scope,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(error)) from error
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    if conversation_id is not None:
        attachment = await _chat(request).attach_document(
            context, conversation_id, document.id
        )
        if attachment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return _document_response(document)


@api_router.get("/knowledge/documents")
async def list_documents(
    request: Request, owner_scope: str | None = None
) -> list[DocumentResponse]:
    """List visible knowledge documents and processing status."""
    try:
        documents = await _knowledge(request).list_documents(
            await _context(request), owner_scope
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return [_document_response(item) for item in documents]


@api_router.post("/knowledge/documents/{document_id}/promote")
async def promote_document(
    document_id: UUID, payload: RevokeDocumentRequest, request: Request
) -> DocumentResponse:
    """Promote one personally owned source after exact-name admin confirmation."""
    try:
        document = await _knowledge(request).promote(
            document_id, payload.confirmation_name, await _context(request)
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge document not found.")
    return _document_response(document)


@api_router.get("/knowledge/documents/{document_id}/preview")
async def preview_document_source(
    document_id: UUID,
    chunk_ordinal: int,
    request: Request,
    radius: int = 1,
) -> list[SourcePreviewItemResponse]:
    """Return an ACL-revalidated citation window without leaking adjacent sources."""
    try:
        items = await _knowledge(request).preview(
            document_id, chunk_ordinal, radius, await _context(request)
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    if not items:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Citation source not found.")
    return [
        SourcePreviewItemResponse(
            citation_id=item.citation_id,
            document_id=item.document_id,
            title=item.title,
            content=item.content,
            source_uri=item.source_uri,
            locator=item.locator,
            is_target=item.citation_id.endswith(f":{chunk_ordinal}"),
        )
        for item in items
    ]


@api_router.post("/knowledge/documents/{document_id}/revoke")
async def revoke_document(
    document_id: UUID,
    payload: RevokeDocumentRequest,
    request: Request,
) -> DocumentResponse:
    """Immediately withdraw a source and purge stale derived indexes."""
    try:
        document = await _knowledge(request).revoke(
            document_id, payload.confirmation_name, await _context(request)
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge document not found.")
    return _document_response(document)


@api_router.post("/artifacts/report-drafts", status_code=status.HTTP_201_CREATED)
async def create_report_draft(
    payload: CreateReportDraftRequest,
    request: Request,
) -> ArtifactResponse:
    """Create an authorized versioned report draft without publishing it."""
    try:
        artifact = await _artifacts(request).create_report_draft(
            name=payload.name,
            content=payload.content,
            output_format=payload.output_format,
            project_id=payload.project_id,
            citations=tuple(payload.citations),
            data_lineage=tuple(payload.data_lineage),
            template_id=payload.template_id,
            context=await _context(request),
        )
    except (ValueError, LookupError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return _artifact_response(artifact)


@api_router.post("/artifacts/execution-drafts", status_code=status.HTTP_201_CREATED)
async def create_execution_draft(
    payload: CreateExecutionDraftRequest, request: Request
) -> ArtifactResponse:
    """Create a governed draft for any registered execution-agent output family."""
    try:
        artifact = await _artifacts(request).create_draft(
            name=payload.name,
            content=payload.content,
            artifact_type=ArtifactType(payload.artifact_type),
            output_format=payload.output_format,
            project_id=payload.project_id,
            citations=tuple(payload.citations),
            data_lineage=tuple(payload.data_lineage),
            template_id=payload.template_id,
            context=await _context(request),
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except (ValueError, LookupError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return _artifact_response(artifact)


@api_router.get("/artifacts")
async def list_artifacts(request: Request) -> list[ArtifactResponse]:
    """List artifacts visible through current tenant and project scope."""
    items = await _artifacts(request).list(await _context(request))
    return [_artifact_response(item) for item in items]


@api_router.post("/artifacts/templates", status_code=status.HTTP_201_CREATED)
async def create_artifact_template(
    payload: CreateArtifactTemplateRequest, request: Request
) -> ArtifactTemplateResponse:
    """Create a tenant template as Owner/Admin."""
    try:
        item = await _artifacts(request).create_template(
            name=payload.name,
            body=payload.body,
            artifact_type=ArtifactType(payload.artifact_type),
            output_format=payload.output_format,
            context=await _context(request),
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except (ValueError, LookupError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return _artifact_template_response(item)


@api_router.get("/artifacts/templates")
async def list_artifact_templates(request: Request) -> list[ArtifactTemplateResponse]:
    """List active templates in the caller tenant."""
    items = await _artifacts(request).list_templates(await _context(request))
    return [_artifact_template_response(item) for item in items]


@api_router.get("/artifacts/usage/current-month")
async def artifact_monthly_usage(request: Request) -> ArtifactUsageResponse:
    """Return the tenant's non-sensitive artifact usage totals."""
    usage = await _artifacts(request).monthly_usage(await _context(request))
    return ArtifactUsageResponse(
        artifact_count=usage.artifact_count,
        stored_bytes=usage.stored_bytes,
        input_units=usage.input_units,
        output_units=usage.output_units,
        estimated_cost_micros=usage.estimated_cost_micros,
    )


@api_router.put("/artifacts/{artifact_id}/legal-hold")
async def set_artifact_legal_hold(
    artifact_id: UUID, payload: ArtifactLegalHoldRequest, request: Request
) -> ArtifactRetentionResponse:
    """Set or release legal hold as an organization administrator."""
    try:
        item = await _artifacts(request).set_legal_hold(
            artifact_id, enabled=payload.enabled, context=await _context(request)
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    return ArtifactRetentionResponse(
        artifact_id=item.artifact_id,
        retention_until=item.retention_until,
        legal_hold=item.legal_hold,
        purged_at=item.purged_at,
    )


@api_router.post("/artifacts/retention/purge")
async def purge_expired_artifacts(
    payload: ArtifactPurgeRequest, request: Request
) -> ArtifactPurgeResponse:
    """Execute one bounded, hold-aware retention sweep."""
    try:
        identifiers = await _artifacts(request).purge_expired(
            await _context(request), payload.limit
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return ArtifactPurgeResponse(purged_artifact_ids=list(identifiers))


@api_router.post("/artifacts/{artifact_id}/actions/validate")
async def validate_artifact_action(
    artifact_id: UUID, payload: ValidateArtifactActionRequest, request: Request
) -> ArtifactActionResponse:
    """Validate an approved action without causing the external side effect."""
    try:
        item = await _artifacts(request).validate_action(
            artifact_id=artifact_id,
            action=payload.action,
            destination_type=payload.destination_type,
            destination=payload.destination,
            idempotency_key=payload.idempotency_key,
            context=await _context(request),
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if item is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Approved artifact not found."
        )
    return ArtifactActionResponse(
        id=item.id,
        artifact_id=item.artifact_id,
        action=item.action,
        destination_type=item.destination_type,
        status=item.status.value,
        provider=item.provider,
        external_id=item.external_id,
        error_code=item.error_code,
        attempt_count=item.attempt_count,
        max_attempts=item.max_attempts,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@api_router.post("/artifacts/actions/{action_id}/execute")
async def execute_artifact_action(
    action_id: UUID, payload: ExecuteArtifactActionRequest, request: Request
) -> ArtifactActionResponse:
    """Execute through a configured provider; local default is side-effect-free dry-run."""
    try:
        item = await _artifact_execution(request).execute(
            action_id=action_id,
            destination=payload.destination,
            idempotency_key=payload.idempotency_key,
            provider_name=payload.provider,
            context=await _context(request),
        )
    except LookupError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Validated action not found.")
    return ArtifactActionResponse(
        id=item.id,
        artifact_id=item.artifact_id,
        action=item.action,
        destination_type=item.destination_type,
        status=item.status.value,
        provider=item.provider,
        external_id=item.external_id,
        error_code=item.error_code,
        attempt_count=item.attempt_count,
        max_attempts=item.max_attempts,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@api_router.put("/artifacts/action-provider-mappings/current")
async def configure_action_provider_mapping(
    payload: ActionProviderMappingRequest, request: Request
) -> ActionProviderMappingResponse:
    """Configure one exact MCP action mapping for the tenant."""
    try:
        item = await _artifacts(request).configure_action_mapping(
            action=payload.action,
            destination_type=payload.destination_type,
            tool_name=payload.tool_name,
            destination_field=payload.destination_field,
            content_field=payload.content_field,
            active=payload.active,
            context=await _context(request),
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return ActionProviderMappingResponse(
        id=item.id,
        action=item.action,
        destination_type=item.destination_type,
        tool_name=item.tool_name,
        destination_field=item.destination_field,
        content_field=item.content_field,
        active=item.active,
    )


@api_router.post("/artifacts/actions/{action_id}/retry")
async def retry_artifact_action(action_id: UUID, request: Request) -> ArtifactActionResponse:
    """Explicitly revalidate one failed action below its bounded retry limit."""
    try:
        item = await _artifact_execution(request).retry(action_id, await _context(request))
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found.")
    return _artifact_action_response(item)


@api_router.post("/artifacts/actions/{action_id}/compensate")
async def compensate_artifact_action(
    action_id: UUID, request: Request
) -> ArtifactActionResponse:
    """Compensate one succeeded action when its original provider supports it."""
    try:
        item = await _artifact_execution(request).compensate(
            action_id, await _context(request)
        )
    except LookupError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found.")
    return _artifact_action_response(item)


@api_router.get("/artifacts/{artifact_id}/versions/{version_number}/download")
async def download_artifact(
    artifact_id: UUID,
    version_number: int,
    request: Request,
) -> Response:
    """Download an immutable artifact after reauthorization and checksum validation."""
    item = await _artifacts(request).download(artifact_id, version_number, await _context(request))
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    return Response(
        content=item.content,
        media_type=item.content_type,
        headers={"Content-Disposition": f'attachment; filename="{item.filename}"'},
    )


@api_router.post("/artifacts/{artifact_id}/review", status_code=status.HTTP_201_CREATED)
async def submit_artifact_review(artifact_id: UUID, request: Request) -> ArtifactReviewResponse:
    """Submit a draft for independent review."""
    try:
        review = await _artifacts(request).submit_review(artifact_id, await _context(request))
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    return _artifact_review_response(review)


@api_router.post("/artifacts/{artifact_id}/review/decision")
async def decide_artifact_review(
    artifact_id: UUID,
    payload: ArtifactReviewDecisionRequest,
    request: Request,
) -> ArtifactReviewResponse:
    """Record an administrator review without allowing self-approval."""
    try:
        review = await _artifacts(request).decide_review(
            artifact_id,
            ReviewDecision(payload.decision),
            payload.comment,
            await _context(request),
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    return _artifact_review_response(review)


@api_router.post("/artifacts/{artifact_id}/publish")
async def publish_artifact(artifact_id: UUID, request: Request) -> ArtifactResponse:
    """Publish an approved artifact; no provider side effect occurs in F8.1."""
    try:
        artifact = await _artifacts(request).publish(artifact_id, await _context(request))
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    return _artifact_response(artifact)


@api_router.get("/artifacts/policy/current")
async def get_artifact_policy(request: Request) -> ArtifactPolicyResponse:
    """Return the caller tenant's effective server-owned artifact policy."""
    policy = await _artifacts(request).get_policy(await _context(request))
    return _artifact_policy_response(policy)


@api_router.put("/artifacts/policy/current")
async def configure_artifact_policy(
    payload: ArtifactPolicyRequest, request: Request
) -> ArtifactPolicyResponse:
    """Configure bounded organization artifact rules as Owner/Admin."""
    try:
        policy = await _artifacts(request).configure_policy(
            brand_name=payload.brand_name,
            footer_text=payload.footer_text,
            require_classification_mark=payload.require_classification_mark,
            retention_days=payload.retention_days,
            monthly_artifact_limit=payload.monthly_artifact_limit,
            context=await _context(request),
        )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return _artifact_policy_response(policy)


@api_router.post(
    "/integrations/connections",
    status_code=status.HTTP_201_CREATED,
)
async def create_integration_connection(
    payload: CreateIntegrationConnectionRequest,
    request: Request,
) -> IntegrationConnectionResponse:
    """Create an encrypted connection in the caller's tenant."""
    try:
        connection = await _integrations(request).create(
            provider=IntegrationProvider(payload.provider),
            name=payload.name,
            endpoint_url=payload.endpoint_url,
            authorization=payload.authorization,
            scope=ConnectionScope(payload.scope),
            context=await _context(request),
        )
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration denied.") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return _integration_response(connection)


@api_router.get("/integrations/connections")
async def list_integration_connections(
    request: Request,
) -> list[IntegrationConnectionResponse]:
    """List visible connections without provider credentials."""
    connections = await _integrations(request).list(await _context(request))
    return [_integration_response(item) for item in connections]


@api_router.delete("/integrations/connections/{connection_id}")
async def disable_integration_connection(
    connection_id: UUID,
    request: Request,
) -> IntegrationConnectionResponse:
    """Disable a visible connection and erase its stored authorization material."""
    try:
        connection = await _integrations(request).disable(connection_id, await _context(request))
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    return _integration_response(connection)


@api_router.post("/integrations/connections/{connection_id}/revoke")
async def revoke_integration_connection(
    connection_id: UUID, request: Request
) -> IntegrationConnectionResponse:
    """Revoke use and erase credentials immediately."""
    try:
        connection = await _integrations(request).revoke(connection_id, await _context(request))
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    return _integration_response(connection)


@api_router.put("/integrations/connections/{connection_id}/credential")
async def reconnect_integration_connection(
    connection_id: UUID, payload: ReconnectIntegrationRequest, request: Request
) -> IntegrationConnectionResponse:
    """Rotate write-only credentials and reactivate the connection."""
    try:
        connection = await _integrations(request).reconnect(
            connection_id, payload.authorization, await _context(request)
        )
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    return _integration_response(connection)


@api_router.post("/integrations/connections/{connection_id}/verify")
async def verify_integration_connection(
    connection_id: UUID,
    request: Request,
) -> IntegrationVerificationResponse:
    """Verify a connection using bounded live MCP discovery."""
    try:
        tool_count = await _integrations(request).verify(connection_id, await _context(request))
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except Exception as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Provider connection verification failed.",
        ) from error
    if tool_count is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    return IntegrationVerificationResponse(
        connection_id=connection_id,
        status="connected",
        tool_count=tool_count,
    )


@api_router.get("/integrations/connections/{connection_id}/grants")
async def list_connection_grants(
    connection_id: UUID, request: Request
) -> list[ConnectionToolGrantResponse]:
    """List scoped tool grants to an authorized connection manager."""
    try:
        grants = await _integrations(request).list_grants(connection_id, await _context(request))
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    if grants is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    return [_connection_grant_response(grant) for grant in grants]


@api_router.put("/integrations/connections/{connection_id}/grants")
async def set_connection_grant(
    connection_id: UUID, payload: ConnectionToolGrantRequest, request: Request
) -> ConnectionToolGrantResponse:
    """Create or update one explicit subject/tool capability."""
    from tactiqo.integrations.domain.models import (  # noqa: PLC0415
        GrantSubjectType,
        ToolPermission,
    )

    try:
        grant = await _integrations(request).set_grant(
            connection_id,
            subject_type=GrantSubjectType(payload.subject_type),
            subject_id=payload.subject_id,
            tool_name=payload.tool_name,
            permission=ToolPermission(payload.permission),
            context=await _context(request),
        )
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    return _connection_grant_response(grant)


@api_router.post("/integrations/oauth/{provider}/start")
async def start_integration_oauth(
    provider: IntegrationProvider,
    payload: StartIntegrationOAuthRequest,
    request: Request,
) -> StartIntegrationOAuthResponse:
    """Start provider consent with signed state and PKCE S256."""
    try:
        result = await _integration_oauth(request).start(
            provider,
            payload.name,
            ConnectionScope(payload.scope),
            await _context(request),
        )
    except IntegrationAdministrationDeniedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except (OAuthFlowError, ValueError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    except Exception as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "OAuth provider initialization failed."
        ) from error
    return StartIntegrationOAuthResponse(authorization_url=result.authorization_url)


@api_router.get("/integrations/oauth/{provider}/callback")
async def finish_integration_oauth(
    provider: IntegrationProvider,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Finish provider consent without rendering or returning any token."""
    service = _integration_oauth(request)
    if error or not code or not state:
        return RedirectResponse(service.error_url, status_code=status.HTTP_303_SEE_OTHER)
    try:
        await service.callback(provider, code, state, await _context(request))
    except (
        IntegrationAdministrationDeniedError,
        OAuthFlowError,
        httpx.HTTPError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return RedirectResponse(service.error_url, status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(service.success_url, status_code=status.HTTP_303_SEE_OTHER)


def _conversation_response(item: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=item.id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _message_response(item: Message) -> MessageResponse:
    return MessageResponse(
        id=item.id,
        role=item.role.value,
        content=item.content,
        created_at=item.created_at,
    )


def _run_response(item: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=item.id,
        conversation_id=item.conversation_id,
        status=item.status.value,
        current_step=item.current_step,
        cancel_requested=item.cancel_requested,
        error_code=item.error_code,
        created_at=item.created_at,
        updated_at=item.updated_at,
        completed_at=item.completed_at,
    )


def _job_response(item: Job) -> JobResponse:
    return JobResponse(
        id=item.id,
        run_id=item.run_id,
        plan_id=item.plan_id,
        step_id=item.step_id,
        kind=item.kind.value,
        risk=item.risk.value,
        status=item.status.value,
        priority=item.priority,
        progress_stage=item.progress.stage,
        completed_units=item.progress.completed_units,
        total_units=item.progress.total_units,
        cancel_requested=item.cancel_requested,
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _approval_response(item: ApprovalRequest) -> ApprovalResponse:
    return ApprovalResponse(
        id=item.id,
        run_id=item.run_id,
        tool_name=item.tool_name,
        arguments=item.arguments,
        status=item.status.value,
        created_at=item.created_at,
        decided_at=item.decided_at,
    )


def _document_response(item: KnowledgeDocument) -> DocumentResponse:
    return DocumentResponse(
        id=item.id,
        name=item.name,
        content_type=item.content_type,
        source_uri=item.source_uri,
        status=item.status.value,
        project_id=item.project_id,
        domain=item.domain.value,
        purpose=item.purpose.value,
        owner_scope=item.owner_scope,
        classification=item.classification,
        parser_name=item.parser_name,
        error_code=item.error_code,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _artifact_response(item: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=item.id,
        name=item.name,
        artifact_type=item.artifact_type.value,
        status=item.status.value,
        classification=item.classification,
        project_id=item.project_id,
        current_version=item.current_version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _artifact_review_response(item: ArtifactReview) -> ArtifactReviewResponse:
    return ArtifactReviewResponse(
        id=item.id,
        artifact_id=item.artifact_id,
        version_number=item.version_number,
        requested_by=item.requested_by,
        decision=item.decision.value,
        decided_by=item.decided_by,
        comment=item.comment,
        created_at=item.created_at,
        decided_at=item.decided_at,
    )


def _artifact_policy_response(item: OrganizationArtifactPolicy) -> ArtifactPolicyResponse:
    return ArtifactPolicyResponse(
        organization_id=item.organization_id,
        brand_name=item.brand_name,
        footer_text=item.footer_text,
        require_classification_mark=item.require_classification_mark,
        retention_days=item.retention_days,
        monthly_artifact_limit=item.monthly_artifact_limit,
    )


def _artifact_template_response(item: ArtifactTemplate) -> ArtifactTemplateResponse:
    return ArtifactTemplateResponse(
        id=item.id,
        name=item.name,
        artifact_type=item.artifact_type.value,
        output_format=item.output_format,
        body=item.body,
        active=item.active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _artifact_action_response(item: ArtifactActionRun) -> ArtifactActionResponse:
    return ArtifactActionResponse(
        id=item.id,
        artifact_id=item.artifact_id,
        action=item.action,
        destination_type=item.destination_type,
        status=item.status.value,
        provider=item.provider,
        external_id=item.external_id,
        error_code=item.error_code,
        attempt_count=item.attempt_count,
        max_attempts=item.max_attempts,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _integration_response(item: IntegrationConnection) -> IntegrationConnectionResponse:
    return IntegrationConnectionResponse(
        id=item.id,
        provider=item.provider.value,
        name=item.name,
        endpoint_url=item.endpoint_url,
        scope=item.scope.value,
        status=item.status.value,
        organization_id=item.organization_id,
        owner_actor_id=item.owner_actor_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _connection_grant_response(item: ConnectionToolGrant) -> ConnectionToolGrantResponse:
    return ConnectionToolGrantResponse(
        id=item.id,
        connection_id=item.connection_id,
        subject_type=item.subject_type.value,
        subject_id=item.subject_id,
        tool_name=item.tool_name,
        permission=item.permission.value,
        created_by=item.created_by,
        created_at=item.created_at,
    )
