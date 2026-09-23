"""Authorization re-evaluation tests for durable agent runs."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from tactiqo.agents.application.orchestrator import AgentOrchestrator
from tactiqo.chat.domain.models import RunStatus
from tactiqo.shared.domain.execution import ExecutionContext


class WaitingGraph:
    """Expose a checkpoint that represents an interrupted active run."""

    resumed = False

    async def aget_state(self, _config: object) -> SimpleNamespace:
        """Return the persisted delegated context."""
        return SimpleNamespace(values={"context": _context().audit_metadata()})

    async def aupdate_state(self, _config: object, _values: object) -> None:
        """Record an unexpected state update."""
        self.resumed = True

    async def ainvoke(self, _command: object, _config: object) -> None:
        """Record an unexpected graph resume."""
        self.resumed = True


class CurrentContext:
    """Rebuild a still-valid identity whose agent grant was revoked."""

    async def resolve_delegated(self, *_args: str) -> ExecutionContext:
        """Return current identity data with a newer policy version."""
        return ExecutionContext(
            "employee-1", "org-a", "correlation", "internal", "v2", role_codes=("employee",)
        )


class RevokedAgent:
    """Deny the current Planner execution grant."""

    async def authorize_invocation(self, *_args: object) -> None:
        """Represent assignment revocation after the interrupt."""


class RunRepository:
    """Capture the safe failure without requiring orchestration dependencies."""

    def __init__(self) -> None:
        """Initialize empty update and event captures."""
        self.updates: list[tuple[RunStatus, str, str | None]] = []

    async def get_run(self, _run_id: object) -> None:
        """Return no cancelled run marker."""

    async def update_run(
        self,
        _run_id: object,
        status: RunStatus,
        step: str,
        error_code: str | None = None,
    ) -> None:
        """Capture the terminal transition."""
        self.updates.append((status, step, error_code))

    async def append_event(self, *_args: object) -> None:
        """Accept the sanitized failure event."""


def _context() -> ExecutionContext:
    return ExecutionContext(
        "employee-1", "org-a", "correlation", "internal", "v1", role_codes=("employee",)
    )


@pytest.mark.anyio
async def test_revocation_blocks_active_run_resume() -> None:
    """A checkpoint cannot resume after its Planner execution grant is revoked."""
    graph = WaitingGraph()
    chat = RunRepository()
    orchestrator = object.__new__(AgentOrchestrator)
    orchestrator._graph = graph  # noqa: SLF001 - isolate the resume boundary
    orchestrator._context_resolver = CurrentContext()  # noqa: SLF001
    orchestrator._agent_authorizer = RevokedAgent()  # noqa: SLF001
    orchestrator._chat = chat  # noqa: SLF001

    await orchestrator.resume(uuid4())

    assert graph.resumed is False
    assert chat.updates == [(RunStatus.FAILED, "failed", "agent_agent_assignment_denied")]
