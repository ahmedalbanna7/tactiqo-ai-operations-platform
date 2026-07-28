"""Bounded task supervisor retaining references to in-process graph runs."""

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

from tactiqo.agents.application.orchestrator import AgentOrchestrator
from tactiqo.shared.domain.execution import ExecutionContext


class AgentTaskSupervisor:
    """Run a bounded number of local F1 workflows and shut them down cleanly."""

    def __init__(self, orchestrator: AgentOrchestrator, maximum_concurrency: int) -> None:
        """Configure an orchestrator and its concurrency ceiling."""
        self._orchestrator = orchestrator
        self._semaphore = asyncio.Semaphore(maximum_concurrency)
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def start(self, run_id: UUID, message: str, context: ExecutionContext) -> None:
        """Schedule a new run if it is not already active."""
        self._schedule(run_id, self._orchestrator.start(run_id, message, context))

    def resume(self, run_id: UUID) -> None:
        """Schedule a checkpoint resume after an approval decision."""
        self._schedule(run_id, self._orchestrator.resume(run_id))

    async def shutdown(self) -> None:
        """Cancel active tasks during process shutdown."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _schedule(self, run_id: UUID, operation: Coroutine[Any, Any, None]) -> None:
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            operation.close()
            return
        task = asyncio.create_task(self._bounded(operation), name=f"agent-run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    async def _bounded(self, operation: Coroutine[Any, Any, None]) -> None:
        async with self._semaphore:
            await operation
