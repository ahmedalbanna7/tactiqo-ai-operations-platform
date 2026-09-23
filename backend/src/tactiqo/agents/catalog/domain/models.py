"""Stable agent categories, versions, capabilities, and effective cards."""

from dataclasses import dataclass, field
from enum import StrEnum

from tactiqo.authorization.domain.models import PolicyAction, PolicyObligation


class AgentCategory(StrEnum):
    """User-facing categories for the initial operational agent packs."""

    COORDINATION = "coordination"
    BUSINESS = "business"
    INDUSTRY = "industry"
    EXECUTION_CONTENT = "execution_content"
    DATA_BI = "data_bi"
    AUTOMATION_INTEGRATIONS = "automation_integrations"
    KNOWLEDGE_RESEARCH = "knowledge_research"
    SAFETY_RISK_GOVERNANCE = "safety_risk_governance"


class AgentRisk(StrEnum):
    """Highest materiality an agent version may request."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Stable agent identity independent from versioned behavior."""

    code: str
    name: str
    description: str
    category: AgentCategory


@dataclass(frozen=True, slots=True)
class AgentVersion:
    """Immutable prompt/config and capability contract version."""

    agent_code: str
    version: str
    prompt_template: str
    configuration: dict[str, str]
    capabilities: tuple[str, ...]
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    risk: AgentRisk


@dataclass(frozen=True, slots=True)
class AgentCandidate:
    """Installed agent metadata before policy filtering."""

    definition: AgentDefinition
    version: AgentVersion
    classification: str = "internal"
    department_id: str | None = None
    team_id: str | None = None
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class EffectiveAgentCard:
    """Only agent information an employee is permitted to discover."""

    code: str
    name: str
    description: str
    category: AgentCategory
    version: str
    capabilities: tuple[str, ...]
    allowed_actions: tuple[PolicyAction, ...]
    obligations: tuple[PolicyObligation, ...] = field(default_factory=tuple)


INITIAL_AGENT_PACKS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        "chat_assistant",
        "Chat Assistant",
        "Handles authorized conversational requests without unnecessary planning.",
        AgentCategory.COORDINATION,
    ),
    AgentDefinition(
        "planner", "Planner Agent", "Plans and delegates bounded work.", AgentCategory.COORDINATION
    ),
    AgentDefinition(
        "executive_strategy",
        "Executive & Strategy Agent",
        "Supports authorized strategy work.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "pmo",
        "PMO & Project Management Agent",
        "Plans and reports project delivery.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "construction",
        "Construction Operations Agent",
        "Supports construction operations.",
        AgentCategory.INDUSTRY,
    ),
    AgentDefinition(
        "events", "Events Operations Agent", "Coordinates event operations.", AgentCategory.INDUSTRY
    ),
    AgentDefinition(
        "risk_compliance",
        "Risk & Compliance Agent",
        "Reviews risk and compliance evidence.",
        AgentCategory.SAFETY_RISK_GOVERNANCE,
    ),
    AgentDefinition(
        "product_software",
        "Product & Software Development Agent",
        "Supports product and software delivery.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "automation_integrations",
        "Automation & Integrations Agent",
        "Builds approved automations and integrations.",
        AgentCategory.AUTOMATION_INTEGRATIONS,
    ),
    AgentDefinition(
        "finance", "Finance Agent", "Supports authorized finance workflows.", AgentCategory.BUSINESS
    ),
    AgentDefinition(
        "it_operations",
        "IT Operations Agent",
        "Supports IT service operations.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "people_hr",
        "People & HR Agent",
        "Supports authorized people operations.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "procurement_vendors",
        "Procurement & Vendors Agent",
        "Supports procurement and vendor workflows.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "legal",
        "Legal Agent",
        "Supports authorized legal workflows.",
        AgentCategory.SAFETY_RISK_GOVERNANCE,
    ),
    AgentDefinition(
        "sales_crm",
        "Sales & CRM Agent",
        "Supports sales and CRM operations.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "marketing",
        "Marketing Agent",
        "Drafts and coordinates marketing content.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "customer_success",
        "Customer Support & Success Agent",
        "Supports customer operations.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "operations_facilities",
        "Operations & Facilities Agent",
        "Supports facilities operations.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "quality_hse",
        "Quality & HSE Agent",
        "Supports quality, safety, and HSE review.",
        AgentCategory.SAFETY_RISK_GOVERNANCE,
    ),
    AgentDefinition(
        "knowledge_documents",
        "Knowledge & Documents Agent",
        "Finds and reviews authorized documents.",
        AgentCategory.KNOWLEDGE_RESEARCH,
    ),
    AgentDefinition(
        "data_analytics",
        "Data & Analytics Agent",
        "Queries authorized SQL, NoSQL, warehouse, and analytical data tools.",
        AgentCategory.DATA_BI,
    ),
    AgentDefinition(
        "communications",
        "Communications Agent",
        "Drafts authorized communications.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "email_execution",
        "Email Execution Agent",
        "Drafts, reviews, schedules, and sends approved email through assigned tools.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "report_execution",
        "Report Execution Agent",
        "Builds cited governed reports from authorized sources.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "document_execution",
        "Document Execution Agent",
        "Produces governed documents and controlled PDF-ready drafts.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "presentation_execution",
        "Presentation Execution Agent",
        "Produces reviewed presentations from authorized material.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "spreadsheet_execution",
        "Spreadsheet Execution Agent",
        "Builds and validates governed analytical workbooks.",
        AgentCategory.DATA_BI,
    ),
    AgentDefinition(
        "power_bi_execution",
        "Power BI Execution Agent",
        "Prepares governed semantic-model and dashboard publication workflows.",
        AgentCategory.DATA_BI,
    ),
    AgentDefinition(
        "image_execution",
        "Image Execution Agent",
        "Creates and edits approved branded visual assets through assigned providers.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "video_execution",
        "Video Execution Agent",
        "Coordinates storyboard, captions, rendering, and approved video export.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "meeting_calendar_execution",
        "Meetings & Calendar Agent",
        "Prepares agendas, scheduling, minutes, decisions, and approved follow-ups.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "data_operations_execution",
        "Data Operations Agent",
        "Validates governed cleanup, mapping, import, export, and synchronization jobs.",
        AgentCategory.DATA_BI,
    ),
    AgentDefinition(
        "social_campaign_execution",
        "Social & Campaign Agent",
        "Drafts, reviews, schedules, and publishes approved campaign content.",
        AgentCategory.EXECUTION_CONTENT,
    ),
    AgentDefinition(
        "department_operations",
        "Department Operations Agent",
        "Generic pack for future departments.",
        AgentCategory.BUSINESS,
    ),
    AgentDefinition(
        "review_safety_recovery",
        "Review, Safety & Recovery Agent",
        "Reviews outputs and manages guarded fallback.",
        AgentCategory.SAFETY_RISK_GOVERNANCE,
    ),
)
