"""Strict transport schemas for system and F1 functional endpoints."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class StrictSchema(BaseModel):
    """Forbid accidental transport fields at every public boundary."""

    model_config = ConfigDict(extra="forbid")


class ComponentHealthResponse(StrictSchema):
    """Expose a safe readiness result for one dependency."""

    name: str
    status: str
    detail: str | None = None


class HealthResponse(StrictSchema):
    """Expose service liveness or aggregate readiness."""

    status: str
    service: str
    version: str
    environment: str
    components: list[ComponentHealthResponse] = Field(default_factory=list)


class ServiceInfoResponse(StrictSchema):
    """Expose non-sensitive service identity information."""

    name: str
    version: str
    environment: str


class SessionResponse(StrictSchema):
    """Secret-free browser session metadata."""

    id: UUID
    assurance: str
    created_at: datetime
    expires_at: datetime
    current: bool


class CreateDepartmentRequest(StrictSchema):
    """Create one department within the server-derived tenant."""

    code: str = Field(pattern=r"^[A-Z0-9-]{2,32}$")
    name: str = Field(min_length=2, max_length=160)
    classification_ceiling: str = Field(default="internal", max_length=64)
    manager_user_id: UUID | None = None


class DepartmentResponse(StrictSchema):
    """Minimal department result without hidden membership data."""

    id: UUID
    code: str
    name: str


class CreateTeamRequest(StrictSchema):
    """Create a team under exactly one department."""

    department_id: UUID
    name: str = Field(min_length=2, max_length=160)
    manager_user_id: UUID | None = None


class CreateProjectRequest(StrictSchema):
    """Create a project under one owning department."""

    department_id: UUID
    code: str = Field(pattern=r"^[A-Z0-9-]{2,32}$")
    name: str = Field(min_length=2, max_length=160)
    manager_user_id: UUID | None = None


class AssignPrivilegedRoleRequest(StrictSchema):
    """Owner-only privileged role assignment."""

    user_id: UUID
    role: Literal["organization_admin", "integration_manager"]


class AssignMembershipRequest(StrictSchema):
    """Assign an organization member to one hierarchy unit."""

    user_id: UUID


class SetMemberStatusRequest(StrictSchema):
    """Owner-controlled lifecycle transition for an organization member."""

    status: Literal["active", "suspended"]


class RoleHistoryResponse(StrictSchema):
    """Safe, bounded role assignment history without credentials."""

    id: UUID
    role_code: str
    scope_type: str
    scope_id: str | None
    valid_from: datetime
    valid_until: datetime | None
    revoked_at: datetime | None
    revoked_by: UUID | None
    assigned_by: UUID


class EffectiveAccessPreviewAgentResponse(StrictSchema):
    """An agent currently visible to the target; denied agent metadata is omitted."""

    code: str
    name: str
    category: str
    allowed_actions: tuple[str, ...]
    reason_code: Literal["allowed"]


class EffectiveAccessActionChangeResponse(StrictSchema):
    """Allowed action delta for an agent present in both policy evaluations."""

    code: str
    name: str
    gained_actions: tuple[str, ...]
    lost_actions: tuple[str, ...]


class EffectiveToolGrantPreviewResponse(StrictSchema):
    """Active provider tool grant without connection or credential identifiers."""

    provider: Literal["jira", "slack"]
    connection_name: str
    tool_name: str
    permission: Literal["read", "draft", "execute", "administer"]


class EffectiveAccessPreviewResponse(StrictSchema):
    """Current and simulated role or membership access without persistence changes."""

    user_id: UUID
    organization_id: str
    policy_version: str
    evaluated_at: datetime
    scope: Literal[
        "current_agent_access",
        "role_change_agent_access_simulation",
        "membership_change_agent_access_simulation",
    ]
    agents: tuple[EffectiveAccessPreviewAgentResponse, ...]
    proposed_role: str | None
    role_operation: Literal["add", "remove"] | None
    proposed_agents: tuple[EffectiveAccessPreviewAgentResponse, ...]
    gained_agents: tuple[str, ...]
    lost_agents: tuple[str, ...]
    action_changes: tuple[EffectiveAccessActionChangeResponse, ...]
    tool_grants: tuple[EffectiveToolGrantPreviewResponse, ...]
    tools_truncated: bool
    proposed_scope_kind: Literal["department", "team", "project"] | None
    proposed_scope_id: UUID | None
    scope_operation: Literal["add", "remove"] | None


class AccessPreviewScenarioRequest(StrictSchema):
    """Optional, non-persisted role or membership simulation for one current member."""

    role_code: Literal[
        "organization_admin", "integration_manager", "department_manager",
        "team_manager", "project_manager", "employee", "auditor_risk_reviewer",
    ] | None = None
    operation: Literal["add", "remove"] | None = None
    scope_kind: Literal["department", "team", "project"] | None = None
    scope_id: UUID | None = None
    scope_operation: Literal["add", "remove"] | None = None


class TenantLifecycleRequestBody(StrictSchema):
    """Start an owner-controlled high-risk tenant transition."""

    action: Literal["owner_transfer", "suspend", "export", "delete"]
    target_user_id: UUID | None = None
    retention_days: int | None = Field(default=None, ge=7, le=365)


class TenantLifecycleResponse(StrictSchema):
    """Durable secret-free lifecycle request state."""

    id: UUID
    action: str
    status: str


class AgentObligationResponse(StrictSchema):
    """Non-secret enforcement obligation shown with an effective agent."""

    kind: str
    value: str


class EffectiveAgentCardResponse(StrictSchema):
    """Only the agent metadata and actions visible to the caller."""

    code: str
    name: str
    description: str
    category: str
    version: str
    capabilities: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    obligations: tuple[AgentObligationResponse, ...]


class SettingsSectionResponse(StrictSchema):
    """Authorized Company Settings navigation item."""

    code: str
    label: str


class CompanyUnitResponse(StrictSchema):
    """Non-secret tenant organizational unit shown to administrators."""

    id: UUID
    kind: Literal["department", "team", "project"]
    code: str
    name: str
    department_id: UUID | None
    manager_user_id: UUID | None
    classification_ceiling: str | None
    status: str


class CompanyPersonResponse(StrictSchema):
    """One administrator-visible member without credentials or session data."""

    user_id: UUID
    display_name: str
    email: str | None
    status: str
    classification_clearance: str
    role_codes: tuple[str, ...]


class CreateOrganizationInvitationRequest(StrictSchema):
    """Create a single-use invitation scoped to one department."""

    department_id: UUID


class OrganizationInvitationResponse(StrictSchema):
    """One-time invitation link returned only at creation."""

    id: UUID
    department_id: UUID
    link: str
    expires_at: datetime


class InvitationPreviewResponse(StrictSchema):
    """Safe public invitation details used before entering the IdP login flow."""

    organization_name: str
    department_id: UUID
    department_name: str
    expires_at: datetime


class InvitationTokenRequest(StrictSchema):
    """Accept a bearer token through the request body rather than URL/log paths."""

    token: str = Field(min_length=40, max_length=128)


class InvitationLoginResponse(StrictSchema):
    """OIDC authorization URL returned after validating an invitation token."""

    authorization_url: str


class InvitationAdminResponse(StrictSchema):
    """Tenant-scoped invitation status without bearer material."""

    id: UUID
    department_id: UUID
    department_name: str
    status: str
    expires_at: datetime


class InstallAgentRequest(StrictSchema):
    """Select one immutable catalog version for the organization."""

    agent_code: str = Field(pattern=r"^[a-z0-9_]{2,96}$")
    version: str = Field(min_length=1, max_length=64)


class AgentCatalogItemResponse(StrictSchema):
    """Non-secret catalog entry for administrator settings."""

    code: str
    name: str
    description: str
    category: str
    selected_version: str
    versions: tuple[str, ...]
    installed: bool
    enabled: bool


class SetAgentEnabledRequest(StrictSchema):
    """Change installed agent lifecycle state."""

    enabled: bool


class AgentObligationInput(StrictSchema):
    """One supported post-decision enforcement obligation."""

    kind: Literal["approval", "redaction", "rate_limit", "quota", "step_up"]
    value: str = Field(min_length=1, max_length=160)


class CreateAgentAssignmentRequest(StrictSchema):
    """Assign independent actions and bounded resources to one target."""

    agent_code: str = Field(pattern=r"^[a-z0-9_]{2,96}$")
    target_type: Literal["organization", "role", "department", "team", "project", "user"]
    target_id: str = Field(min_length=1, max_length=128)
    actions: tuple[
        Literal[
            "visible",
            "use",
            "read",
            "draft",
            "execute",
            "publish",
            "administer",
            "approve",
            "export",
        ],
        ...,
    ]
    effect: Literal["allow", "deny"] = "allow"
    classification_ceiling: Literal["public", "internal", "confidential", "restricted"] = "internal"
    data_domains: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    quota: dict[str, int] = Field(default_factory=dict)
    budget: dict[str, int] = Field(default_factory=dict)
    obligations: tuple[AgentObligationInput, ...] = ()


class AgentAssignmentResponse(StrictSchema):
    """Identifier for a tenant-owned assignment."""

    id: UUID


class AgentAssignmentDetailResponse(StrictSchema):
    """Administrative assignment view without sensitive policy attachments."""

    id: UUID
    agent_code: str
    target_type: str
    target_id: str
    actions: tuple[str, ...]
    effect: str
    classification_ceiling: str
    active: bool


class SetAgentApprovalChainRequest(StrictSchema):
    """Configure ordered approver selectors for one bounded agent action."""

    agent_code: str = Field(pattern=r"^[a-z0-9_]{2,96}$")
    action: Literal[
        "visible", "use", "read", "draft", "execute", "publish", "administer", "approve", "export"
    ]
    risk: Literal["low", "medium", "high", "critical"]
    target_system: str = Field(default="*", min_length=1, max_length=96)
    approver_steps: tuple[str, ...] = Field(min_length=1, max_length=12)


class AIProfileRequest(StrictSchema):
    """Owner configuration for one provider-neutral AI profile."""

    name: Literal[
        "default_reasoning_llm",
        "fast_chat_llm",
        "structured_extraction_llm",
        "openai_visual_llm",
        "claude_analysis_llm",
        "multilingual_embedding_model",
    ]
    kind: Literal["llm", "embedding"]
    provider: Literal["lm_studio", "openai", "claude"] = "lm_studio"
    model: str = Field(min_length=1, max_length=256)
    endpoint: str = Field(
        default="http://host.docker.internal:1234/v1", min_length=10, max_length=512
    )
    secret_reference: str | None = Field(default=None, max_length=256)
    timeout_seconds: int = Field(default=120, ge=5, le=600)
    maximum_retries: int = Field(default=1, ge=0, le=3)
    maximum_concurrency: int = Field(default=1, ge=1, le=16)
    daily_unit_limit: int = Field(default=1_000_000, ge=1_000, le=1_000_000_000)
    capabilities: tuple[
        Literal[
            "general",
            "fast_chat",
            "reasoning",
            "document_analysis",
            "presentation_composition",
            "structured_extraction",
        ],
        ...,
    ] = ("general",)
    routing_priority: int = Field(default=100, ge=1, le=1000)
    allowed_classifications: tuple[
        Literal["public", "internal", "confidential", "restricted"], ...
    ] | None = None


class AICredentialRequest(StrictSchema):
    """Write-only provider material that is never represented in a response."""

    provider: Literal["openai", "claude"]
    api_key: SecretStr = Field(min_length=20, max_length=512)


class AICredentialResponse(StrictSchema):
    """Opaque reference safe to attach to an AI profile."""

    provider: str
    secret_reference: str


class AIProfileResponse(StrictSchema):
    """Secret-free active profile metadata."""

    name: str
    kind: str
    provider: str
    model: str
    endpoint: str
    status: str
    version: int
    has_secret_reference: bool
    capabilities: tuple[str, ...]
    routing_priority: int
    allowed_classifications: tuple[str, ...]


class AIHealthResponse(StrictSchema):
    """Sanitized provider discovery and connection result."""

    healthy: bool
    latency_ms: int
    models: tuple[str, ...]
    error_code: str | None


class AILLMTestRequest(StrictSchema):
    """Bounded prompt used only by the Owner playground."""

    prompt: str = Field(min_length=1, max_length=2_000)


class AILLMTestResponse(StrictSchema):
    """Text returned by the configured active LLM."""

    text: str


class AIEmbeddingTestRequest(StrictSchema):
    """Bounded multilingual text for the embedding playground."""

    text: str = Field(min_length=1, max_length=2_000)


class AIEmbeddingTestResponse(StrictSchema):
    """Safe embedding diagnostics and a short vector preview."""

    model: str
    embedding_space_id: str
    dimensions: int
    preview: tuple[float, ...]


class CreateConversationRequest(StrictSchema):
    """Create a titled conversation."""

    title: str = Field(default="محادثة جديدة", min_length=1, max_length=160)


class ConversationResponse(StrictSchema):
    """Conversation summary visible in the sidebar."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(StrictSchema):
    """Persisted chat message."""

    id: UUID
    role: str
    content: str
    created_at: datetime


class ChatAttachmentResponse(StrictSchema):
    """Safe document card persisted in one visible conversation."""

    id: UUID
    conversation_id: UUID
    document_id: UUID
    name: str
    status: str
    domain: str
    purpose: str
    created_at: datetime


class SendMessageRequest(StrictSchema):
    """Submit one user turn."""

    content: str = Field(min_length=1, max_length=32_000)


class AgentRunResponse(StrictSchema):
    """Durable workflow status returned to polling and SSE clients."""

    id: UUID
    conversation_id: UUID
    status: str
    current_step: str
    cancel_requested: bool
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class JobResponse(StrictSchema):
    """Scoped durable background-job status and measurable progress."""

    id: UUID
    run_id: UUID
    plan_id: UUID
    step_id: str
    kind: str
    risk: str
    status: str
    priority: int
    progress_stage: str
    completed_units: int
    total_units: int | None
    cancel_requested: bool
    version: int
    created_at: datetime
    updated_at: datetime


class JobMetricsResponse(StrictSchema):
    """Scope-safe background-job lifecycle counters."""

    counts: dict[str, int]


class ApprovalDecisionRequest(StrictSchema):
    """Human decision for a material MCP action."""

    decision: Literal["approved", "rejected"]


class ApprovalResponse(StrictSchema):
    """Public state of a scoped approval request."""

    id: UUID
    run_id: UUID
    tool_name: str
    arguments: dict[str, Any]
    status: str
    created_at: datetime
    decided_at: datetime | None


class DocumentResponse(StrictSchema):
    """Canonical knowledge document processing state."""

    id: UUID
    name: str
    content_type: str
    source_uri: str
    status: str
    project_id: str | None
    domain: str
    purpose: str
    owner_scope: Literal["personal", "organization"]
    classification: str
    parser_name: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class SourcePreviewItemResponse(StrictSchema):
    """One authorized source fragment in a bounded citation preview."""

    citation_id: str
    document_id: UUID
    title: str
    content: str
    source_uri: str
    locator: dict[str, Any]
    is_target: bool


class RevokeDocumentRequest(StrictSchema):
    """Explicit confirmation required before withdrawing indexed knowledge."""

    confirmation_name: str = Field(min_length=1, max_length=255)


class CreateReportDraftRequest(StrictSchema):
    """Create a governed report draft; publication is never implicit."""

    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)
    output_format: Literal["markdown"] = "markdown"
    project_id: str | None = Field(default=None, max_length=128)
    citations: list[str] = Field(default_factory=list, max_length=100)
    data_lineage: list[str] = Field(default_factory=list, max_length=100)
    template_id: UUID | None = None


class CreateExecutionDraftRequest(StrictSchema):
    """Create a draft-only output through one execution-agent family."""

    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)
    artifact_type: Literal[
        "report", "document", "presentation", "spreadsheet", "image", "video",
        "email", "power_bi", "automation"
    ]
    output_format: Literal["markdown", "docx", "pptx", "xlsx"] = "markdown"
    project_id: str | None = Field(default=None, max_length=128)
    citations: list[str] = Field(default_factory=list, max_length=100)
    data_lineage: list[str] = Field(default_factory=list, max_length=100)
    template_id: UUID | None = None


class ArtifactResponse(StrictSchema):
    """Secret-free current artifact state."""

    id: UUID
    name: str
    artifact_type: str
    status: str
    classification: str
    project_id: str | None
    current_version: int
    created_at: datetime
    updated_at: datetime


class ArtifactReviewDecisionRequest(StrictSchema):
    """Independent reviewer decision and bounded rationale."""

    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=2000)


class ArtifactReviewResponse(StrictSchema):
    """Auditable decision state without artifact content."""

    id: UUID
    artifact_id: UUID
    version_number: int
    requested_by: str
    decision: str
    decided_by: str | None
    comment: str | None
    created_at: datetime
    decided_at: datetime | None


class ArtifactPolicyRequest(StrictSchema):
    """Bounded tenant brand, marking, retention, and quota configuration."""

    brand_name: str = Field(min_length=1, max_length=120)
    footer_text: str = Field(default="", max_length=500)
    require_classification_mark: bool = True
    retention_days: int = Field(ge=1, le=3650)
    monthly_artifact_limit: int = Field(ge=1, le=100_000)


class ArtifactPolicyResponse(StrictSchema):
    """Current non-secret artifact production policy."""

    organization_id: str
    brand_name: str
    footer_text: str
    require_classification_mark: bool
    retention_days: int
    monthly_artifact_limit: int


class CreateArtifactTemplateRequest(StrictSchema):
    """Create a reusable tenant-owned artifact template."""

    name: str = Field(min_length=1, max_length=120)
    artifact_type: Literal["report"] = "report"
    output_format: Literal["markdown"] = "markdown"
    body: str = Field(min_length=1, max_length=100_000)


class ArtifactTemplateResponse(StrictSchema):
    """Safe reusable template metadata and body."""

    id: UUID
    name: str
    artifact_type: str
    output_format: str
    body: str
    active: bool
    created_at: datetime
    updated_at: datetime


class ArtifactUsageResponse(StrictSchema):
    """Current-month non-sensitive artifact metering totals."""

    artifact_count: int
    stored_bytes: int
    input_units: int
    output_units: int
    estimated_cost_micros: int


class ArtifactLegalHoldRequest(StrictSchema):
    """Explicit organization-admin legal-hold decision."""

    enabled: bool


class ArtifactRetentionResponse(StrictSchema):
    """Safe artifact retention state."""

    artifact_id: UUID
    retention_until: datetime | None
    legal_hold: bool
    purged_at: datetime | None


class ArtifactPurgeRequest(StrictSchema):
    """Bounded explicit retention sweep request."""

    limit: int = Field(default=25, ge=1, le=100)


class ArtifactPurgeResponse(StrictSchema):
    """Identifiers successfully purged during one bounded sweep."""

    purged_artifact_ids: list[UUID]


class ValidateArtifactActionRequest(StrictSchema):
    """Destination-aware, idempotent execution preflight."""

    action: Literal["send", "publish", "activate", "export", "schedule"]
    destination_type: Literal["email", "channel", "workspace", "site", "project", "file"]
    destination: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ArtifactActionResponse(StrictSchema):
    """Secret-free execution action state."""

    id: UUID
    artifact_id: UUID
    action: str
    destination_type: str
    status: str
    provider: str | None
    external_id: str | None
    error_code: str | None
    attempt_count: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime


class ExecuteArtifactActionRequest(StrictSchema):
    """Execute an already validated destination-bound action."""

    destination: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)
    provider: Literal["dry_run", "mcp"] = "dry_run"


class ActionProviderMappingRequest(StrictSchema):
    """Map a governed action to one exact qualified MCP tool."""

    action: Literal["send", "publish", "activate", "export", "schedule"]
    destination_type: Literal["email", "channel", "workspace", "site", "project", "file"]
    tool_name: str = Field(min_length=1, max_length=256)
    destination_field: str = Field(min_length=1, max_length=96)
    content_field: str = Field(min_length=1, max_length=96)
    active: bool = True


class ActionProviderMappingResponse(StrictSchema):
    """Non-secret tenant MCP action mapping."""

    id: UUID
    action: str
    destination_type: str
    tool_name: str
    destination_field: str
    content_field: str
    active: bool


class CreateIntegrationConnectionRequest(StrictSchema):
    """Create a tenant-scoped Jira or Slack MCP connection."""

    provider: Literal["jira", "slack"]
    name: str = Field(min_length=1, max_length=120)
    endpoint_url: str = Field(min_length=12, max_length=512)
    authorization: str = Field(min_length=1, max_length=8192, repr=False)
    scope: Literal["organization", "personal"] = "organization"


class ReconnectIntegrationRequest(StrictSchema):
    """Write-only replacement authorization for reconnect or rotation."""

    authorization: str = Field(min_length=1, max_length=8192, repr=False)


class IntegrationConnectionResponse(StrictSchema):
    """Secret-free connection status returned to clients."""

    id: UUID
    provider: str
    name: str
    endpoint_url: str
    scope: str
    status: str
    organization_id: str
    owner_actor_id: str | None
    created_at: datetime
    updated_at: datetime


class IntegrationVerificationResponse(StrictSchema):
    """Result of a live MCP discovery check."""

    connection_id: UUID
    status: Literal["connected"]
    tool_count: int


class ConnectionToolGrantRequest(StrictSchema):
    """Assign one MCP tool capability to an organization subject."""

    subject_type: Literal["organization", "department", "team", "project", "agent", "user"]
    subject_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=160)
    permission: Literal["read", "draft", "execute", "administer"]


class ConnectionToolGrantResponse(StrictSchema):
    """Secret-free connection tool grant."""

    id: UUID
    connection_id: UUID
    subject_type: str
    subject_id: str
    tool_name: str
    permission: str
    created_by: str
    created_at: datetime


class StartIntegrationOAuthRequest(StrictSchema):
    """Begin a tenant-scoped provider OAuth consent flow."""

    name: str = Field(min_length=1, max_length=120)
    scope: Literal["organization", "personal"] = "organization"


class StartIntegrationOAuthResponse(StrictSchema):
    """Trusted provider authorization URL for browser navigation."""

    authorization_url: str
