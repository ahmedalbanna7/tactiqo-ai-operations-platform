"""Strict provider-neutral execution plans for F4 orchestration."""

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkClass(StrEnum):
    """Execution lane selected before any planning-model request."""

    FAST = "fast"
    STANDARD = "standard"
    BACKGROUND = "background"


class StepMode(StrEnum):
    """Where a plan step is allowed to execute."""

    FOREGROUND = "foreground"
    BACKGROUND = "background"


class ActionLevel(StrEnum):
    """Maximum materiality declared by a step."""

    READ = "read"
    DRAFT = "draft"
    EXECUTE = "execute"


class WorkEstimate(BaseModel):
    """Content-free workload estimate retained for audit and routing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_characters: int = Field(ge=0)
    file_count: int = Field(default=0, ge=0)
    media_count: int = Field(default=0, ge=0)
    record_count: int = Field(default=0, ge=0)
    tool_count: int = Field(default=0, ge=0)
    agent_count: int = Field(default=1, ge=1)
    step_count: int = Field(default=1, ge=1)
    risk_score: int = Field(default=0, ge=0, le=100)
    approval_count: int = Field(default=0, ge=0)


class DataScope(BaseModel):
    """Exact data readers a step may use; empty means no data access."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rag_collections: tuple[str, ...] = ()
    sql_views: tuple[str, ...] = ()
    nosql_scopes: tuple[str, ...] = ()
    mcp_connections: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()


class PlanBudget(BaseModel):
    """Hard resource ceilings enforced by the supervisor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: int = Field(default=90, ge=1, le=3600)
    maximum_retries: int = Field(default=0, ge=0, le=3)
    maximum_tool_calls: int = Field(default=1, ge=0, le=20)
    maximum_units: int = Field(default=32_000, ge=1)
    monetary_micros: int = Field(default=0, ge=0)


class PlanStep(BaseModel):
    """One authorized, dependency-aware and idempotent unit of work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=96)
    title: str = Field(min_length=1, max_length=160)
    agent_code: str = Field(min_length=1, max_length=96)
    data_reader: str | None = Field(default=None, max_length=96)
    dependencies: tuple[str, ...] = ()
    deliverable: str = Field(min_length=1, max_length=160)
    evidence_required: bool = False
    data_scope: DataScope = Field(default_factory=DataScope)
    action_level: ActionLevel = ActionLevel.READ
    mode: StepMode = StepMode.FOREGROUND
    risk: str = Field(default="low", pattern="^(low|medium|high|critical)$")
    approval_required: bool = False
    idempotency_key: str = Field(min_length=8, max_length=160)
    status: str = Field(default="pending", pattern="^(pending|running|completed|failed|cancelled)$")


class ExecutionPlan(BaseModel):
    """Immutable strict plan consumed by the Supervisor, never executable prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    run_id: UUID
    policy_version: str = Field(min_length=1, max_length=64)
    work_class: WorkClass
    estimate: WorkEstimate
    budget: PlanBudget
    steps: tuple[PlanStep, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_dependencies(self) -> "ExecutionPlan":
        """Reject unknown, duplicate, forward, and self dependencies."""
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen or not set(step.dependencies).issubset(seen):
                message = "plan_dependencies_invalid"
                raise ValueError(message)
            seen.add(step.id)
        return self

    def audit_payload(self) -> dict[str, Any]:
        """Return identifiers and budgets without user or source content."""
        return {
            "plan_id": str(self.id),
            "plan_version": self.version,
            "policy_version": self.policy_version,
            "work_class": self.work_class.value,
            "step_count": len(self.steps),
            "step_ids": [step.id for step in self.steps],
            "agent_codes": [step.agent_code for step in self.steps],
            "timeout_seconds": self.budget.timeout_seconds,
            "maximum_tool_calls": self.budget.maximum_tool_calls,
        }
