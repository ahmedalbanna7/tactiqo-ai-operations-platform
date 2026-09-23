"""Deterministic strict-plan construction and scope compiler."""

from uuid import UUID, uuid5

from tactiqo.agents.application.execution_classifier import ExecutionDecision, ExecutionRoute
from tactiqo.agents.domain.planning import (
    ActionLevel,
    DataScope,
    ExecutionPlan,
    PlanBudget,
    PlanStep,
    StepMode,
    WorkClass,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ToolDefinition, ToolRisk


class StrictPlanBuilder:
    """Build a bounded plan from server-owned routing and discovered entitlements."""

    def __init__(self, maximum_tool_calls: int, timeout_seconds: float) -> None:
        """Configure immutable supervisor ceilings."""
        self._maximum_tool_calls = maximum_tool_calls
        self._timeout_seconds = int(timeout_seconds)

    def build(
        self,
        run_id: UUID,
        decision: ExecutionDecision,
        context: ExecutionContext,
        tools: list[ToolDefinition],
    ) -> ExecutionPlan:
        """Declare only scoped readers/tools already visible to the current actor."""
        tool_names = tuple(tool.name for tool in tools[: self._maximum_tool_calls])
        has_mutation = any(tool.risk is not ToolRisk.READ_ONLY for tool in tools)
        needs_knowledge = decision.route in {
            ExecutionRoute.KNOWLEDGE,
            ExecutionRoute.PLANNED_KNOWLEDGE,
        }
        mode = (
            StepMode.BACKGROUND
            if decision.work_class is WorkClass.BACKGROUND
            else StepMode.FOREGROUND
        )
        scope = DataScope(
            rag_collections=("authorized_knowledge",) if needs_knowledge else (),
            mcp_connections=tuple(sorted({tool.server_label for tool in tools})),
            tools=tool_names,
        )
        step = PlanStep(
            id="step-1",
            title="Execute authorized request",
            agent_code=decision.agent_code,
            data_reader="knowledge_documents" if needs_knowledge else None,
            deliverable="User-visible response or safe deferred status",
            evidence_required=needs_knowledge,
            data_scope=scope,
            action_level=ActionLevel.EXECUTE if tool_names else ActionLevel.READ,
            mode=mode,
            risk="high" if has_mutation else "low",
            approval_required=has_mutation,
            idempotency_key=str(uuid5(run_id, "step-1")),
        )
        return ExecutionPlan(
            id=uuid5(run_id, "plan-v1"),
            run_id=run_id,
            policy_version=context.policy_version,
            work_class=decision.work_class,
            estimate=decision.estimate,
            budget=PlanBudget(
                timeout_seconds=self._timeout_seconds,
                maximum_tool_calls=self._maximum_tool_calls,
            ),
            steps=(step,),
        )


class PlanScopeViolationError(PermissionError):
    """Plan references authority not present in the server-derived context."""


class StrictPlanCompiler:
    """Fail closed before retrieval or tool execution when scope expands."""

    _MAXIMUM_STEPS = 32
    _MAXIMUM_TOOL_CALLS = 20

    @staticmethod
    def compile(plan: ExecutionPlan, context: ExecutionContext) -> ExecutionPlan:
        """Bind the plan to the current policy version and bounded resource limits."""
        if plan.policy_version != context.policy_version:
            message = "plan_policy_version_stale"
            raise PlanScopeViolationError(message)
        if (
            len(plan.steps) > StrictPlanCompiler._MAXIMUM_STEPS
            or plan.budget.maximum_tool_calls > StrictPlanCompiler._MAXIMUM_TOOL_CALLS
        ):
            message = "plan_budget_exceeded"
            raise PlanScopeViolationError(message)
        return plan


class DependencyScheduler:
    """Create safe parallel batches without sharing declared external resources."""

    @staticmethod
    def batches(plan: ExecutionPlan) -> tuple[tuple[str, ...], ...]:
        """Return deterministic dependency waves with resource conflicts serialized."""
        completed: set[str] = set()
        remaining = {step.id: step for step in plan.steps}
        batches: list[tuple[str, ...]] = []
        while remaining:
            ready = [
                step for step in remaining.values() if set(step.dependencies).issubset(completed)
            ]
            if not ready:
                message = "plan_dependency_deadlock"
                raise ValueError(message)
            selected: list[str] = []
            claimed: set[str] = set()
            for step in ready:
                resources = set(step.data_scope.mcp_connections) | set(step.data_scope.tools)
                if resources.isdisjoint(claimed):
                    selected.append(step.id)
                    claimed.update(resources)
            if not selected:
                selected.append(ready[0].id)
            batch = tuple(selected)
            batches.append(batch)
            completed.update(batch)
            for step_id in batch:
                remaining.pop(step_id)
        return tuple(batches)
