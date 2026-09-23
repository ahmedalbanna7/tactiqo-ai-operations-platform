"""F4 strict planning, budget, routing, and policy-binding tests."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from tactiqo.agents.application.execution_classifier import DeterministicExecutionClassifier
from tactiqo.agents.application.planning import (
    DependencyScheduler,
    PlanScopeViolationError,
    StrictPlanBuilder,
    StrictPlanCompiler,
)
from tactiqo.agents.domain.planning import (
    DataScope,
    ExecutionPlan,
    PlanBudget,
    PlanStep,
    StepMode,
    WorkClass,
    WorkEstimate,
)
from tactiqo.shared.domain.execution import ExecutionContext


def _context(policy: str = "v1") -> ExecutionContext:
    return ExecutionContext("actor", "org", "correlation", "internal", policy)


def test_large_media_request_is_background_without_model_classification() -> None:
    """Large media is routed away from latency-sensitive foreground execution."""
    decision = DeterministicExecutionClassifier().classify("حلل فيديو كبير ثم اعمل تقرير وارسله")

    assert decision.work_class is WorkClass.BACKGROUND
    assert decision.estimate.media_count == 1
    assert decision.estimate.approval_count == 1


def test_builder_declares_agent_reader_budget_and_idempotency() -> None:
    """Every generated step carries bounded scope, reader, budget, and identity."""
    decision = DeterministicExecutionClassifier().classify("لخص التقرير من الملف")
    run_id = uuid4()
    plan = StrictPlanBuilder(2, 120).build(run_id, decision, _context(), [])

    assert plan.steps[0].agent_code == "knowledge_documents"
    assert plan.steps[0].data_reader == "knowledge_documents"
    assert plan.steps[0].data_scope.rag_collections == ("authorized_knowledge",)
    assert plan.steps[0].idempotency_key
    assert plan.budget.maximum_tool_calls == len(("first", "second"))


def test_compiler_rejects_resumed_plan_after_policy_change() -> None:
    """A durable plan cannot resume against stale authority."""
    decision = DeterministicExecutionClassifier().classify("ارسل ايميل")
    plan = StrictPlanBuilder(1, 90).build(uuid4(), decision, _context("v1"), [])

    with pytest.raises(PlanScopeViolationError, match="plan_policy_version_stale"):
        StrictPlanCompiler.compile(plan, _context("v2"))


def test_plan_schema_rejects_forward_dependency_and_extra_fields() -> None:
    """Strict plan parsing rejects undeclared fields and invalid dependency graphs."""
    common = {
        "run_id": uuid4(),
        "policy_version": "v1",
        "work_class": WorkClass.STANDARD,
        "estimate": WorkEstimate(input_characters=10),
        "budget": PlanBudget(),
    }
    step = PlanStep(
        id="step-1",
        title="First",
        agent_code="planner",
        dependencies=("step-2",),
        deliverable="draft",
        data_scope=DataScope(),
        mode=StepMode.FOREGROUND,
        idempotency_key="idempotent-step-1",
    )

    with pytest.raises(ValidationError, match="plan_dependencies_invalid"):
        ExecutionPlan(**common, steps=(step,))
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExecutionPlan(**common, steps=(step.model_copy(update={"dependencies": ()}),), hidden=True)


def test_dependency_scheduler_parallelizes_only_independent_resources() -> None:
    """Independent reads share a wave while the same MCP resource is serialized."""
    base = {
        "title": "work",
        "agent_code": "planner",
        "deliverable": "result",
        "idempotency_key": "idempotency-value",
    }
    steps = (
        PlanStep(id="a", data_scope=DataScope(tools=("jira.read",)), **base),
        PlanStep(id="b", data_scope=DataScope(tools=("slack.read",)), **base),
        PlanStep(id="c", data_scope=DataScope(tools=("jira.read",)), **base),
        PlanStep(id="d", dependencies=("a", "b"), **base),
    )
    plan = ExecutionPlan(
        run_id=uuid4(),
        policy_version="v1",
        work_class=WorkClass.STANDARD,
        estimate=WorkEstimate(input_characters=1),
        budget=PlanBudget(),
        steps=steps,
    )

    assert DependencyScheduler.batches(plan) == (("a", "b"), ("c", "d"))
