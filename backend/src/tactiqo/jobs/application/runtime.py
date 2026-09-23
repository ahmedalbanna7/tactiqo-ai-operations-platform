"""Lease-based processor runtime for durable background jobs."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from tactiqo.jobs.application.policy import RetryPolicy
from tactiqo.jobs.application.ports import JobRepository
from tactiqo.jobs.domain.models import Job, JobCheckpoint, JobKind, JobLease, JobStatus
from tactiqo.shared.domain.execution import ExecutionContext

ProgressReporter = Callable[[str, int, int | None], Awaitable[None]]
CheckpointWriter = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ProcessorResult:
    """Reference-only processor output."""

    output_reference: str


class JobProcessor(Protocol):
    """Pluggable processor; new capabilities register without changing runtime."""

    async def process(
        self,
        job: Job,
        context: ExecutionContext,
        checkpoint: JobCheckpoint | None,
        report: ProgressReporter,
        checkpoint_writer: CheckpointWriter,
    ) -> ProcessorResult:
        """Process one idempotent job and return a durable output reference."""


class DelegatedContextResolver(Protocol):
    """Revalidate authority at execution time."""

    async def resolve_delegated(
        self,
        actor_id: str,
        organization_id: str,
        correlation_id: str,
        session_assurance: str,
    ) -> ExecutionContext | None:
        """Resolve current authority for the job's original actor and tenant."""
        ...


class JobWorkerRuntime:
    """Run registered processors with leases, heartbeats, recovery, and bounded retry."""

    def __init__(  # noqa: PLR0913 - runtime dependencies remain explicit
        self,
        repository: JobRepository,
        context_resolver: DelegatedContextResolver,
        processors: Mapping[JobKind, JobProcessor],
        *,
        worker_id: str,
        lease_for: timedelta = timedelta(seconds=60),
        retry_policy: RetryPolicy | None = None,
        maximum_concurrency: int = 2,
    ) -> None:
        """Configure runtime, processor registry, worker identity, and lease policy."""
        self._repository = repository
        self._resolver = context_resolver
        self._processors = processors
        self._worker_id = worker_id
        self._lease_for = lease_for
        self._retry = retry_policy or RetryPolicy()
        self._maximum_concurrency = max(1, maximum_concurrency)

    @property
    def registered_kinds(self) -> tuple[JobKind, ...]:
        """Expose queues this worker may safely consume."""
        return tuple(self._processors)

    async def execute_once(self, kind: JobKind) -> bool:  # noqa: C901
        """Acquire and execute at most one job of a registered kind."""
        await self._repository.recover_expired()
        processor = self._processors.get(kind)
        if processor is None:
            return False
        acquired = await self._repository.acquire(kind, self._worker_id, self._lease_for)
        if acquired is None:
            return False
        job, lease = acquired
        heartbeat = asyncio.create_task(self._heartbeat(lease))
        try:
            current = await self._repository.get_internal(job.id)
            if current is None:
                return True
            if current.cancel_requested:
                await self._repository.finish_attempt(
                    lease, JobStatus.CANCELLED, stage="cancelled", outcome="cancelled"
                )
                return True
            context = await self._resolver.resolve_delegated(
                job.actor_id, job.organization_id, f"job:{job.id}", "delegated"
            )
            if context is None or context.policy_version != job.policy_version:
                await self._repository.finish_attempt(
                    lease,
                    JobStatus.FAILED,
                    stage="authority_revoked",
                    outcome="denied",
                    failure_code="delegated_authority_revoked",
                )
                return True

            async def report(stage: str, completed: int, total: int | None) -> None:
                current_job = await self._repository.get_internal(job.id)
                if current_job is None or current_job.cancel_requested:
                    raise asyncio.CancelledError  # noqa: TRY301
                await self._repository.update_progress(
                    lease, stage=stage, completed_units=completed, total_units=total
                )

            async def save(stage: str, reference: str) -> None:
                await self._repository.save_checkpoint(
                    lease, stage=stage, state_reference=reference
                )

            checkpoint = await self._repository.latest_checkpoint(job.id)
            result = await processor.process(job, context, checkpoint, report, save)
            await self._repository.finish_attempt(
                lease,
                JobStatus.COMPLETED,
                stage="completed",
                outcome="completed",
                output_reference=result.output_reference,
            )
        except asyncio.CancelledError:
            await self._repository.finish_attempt(
                lease, JobStatus.CANCELLED, stage="cancelled", outcome="cancelled"
            )
        except Exception as error:  # noqa: BLE001 - sanitized at the worker boundary
            latest = await self._repository.get_internal(job.id)
            attempt = await self._repository.attempt_count(job.id)
            exhausted = latest is not None and attempt >= latest.maximum_attempts
            await self._repository.finish_attempt(
                lease,
                JobStatus.DEAD_LETTER if exhausted else JobStatus.RETRY_SCHEDULED,
                stage="dead_letter" if exhausted else "retry_scheduled",
                outcome="failed",
                failure_code=type(error).__name__[:96],
                retry_after=None if exhausted else self._retry.delay(attempt),
            )
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        return True

    async def run(self, stop: asyncio.Event, *, poll_seconds: float = 0.5) -> None:
        """Poll registered profiles with bounded concurrency and graceful drain."""
        active: set[asyncio.Task[bool]] = set()
        try:
            while not stop.is_set():
                active = {task for task in active if not task.done()}
                capacity = self._maximum_concurrency - len(active)
                if capacity > 0:
                    for kind in self.registered_kinds[:capacity]:
                        active.add(asyncio.create_task(self.execute_once(kind)))
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=max(0.05, poll_seconds))
        finally:
            if active:
                await asyncio.gather(*active, return_exceptions=True)

    async def _heartbeat(self, lease: JobLease) -> None:
        interval = max(1.0, self._lease_for.total_seconds() / 3)
        while True:
            await asyncio.sleep(interval)
            refreshed = await self._repository.heartbeat(lease, self._lease_for)
            if refreshed is None:
                return
            lease = refreshed
