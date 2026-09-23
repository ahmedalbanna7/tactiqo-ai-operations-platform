"""Durable worker runtime behavior at security and failure boundaries."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

from tactiqo.jobs.application.runtime import JobWorkerRuntime, ProcessorResult
from tactiqo.jobs.domain.models import Job, JobKind, JobLease, JobProgress, JobRisk, JobStatus
from tactiqo.shared.domain.execution import ExecutionContext


def _job() -> Job:
    now = datetime.now(UTC)
    return Job(
        id=uuid4(),
        organization_id="org",
        actor_id="actor",
        run_id=uuid4(),
        plan_id=uuid4(),
        step_id="step",
        kind=JobKind.REPORT_BI,
        risk=JobRisk.LOW,
        status=JobStatus.RUNNING,
        priority=50,
        idempotency_key="key",
        input_reference="tactiqo://runs/input",
        output_reference=None,
        policy_version="v1",
        cancel_requested=False,
        version=2,
        progress=JobProgress("leased", 0, None, now),
        maximum_attempts=3,
        available_at=now,
        created_at=now,
        updated_at=now,
    )


def _context() -> ExecutionContext:
    return ExecutionContext("actor", "org", "correlation", "internal", "v1")


def test_runtime_completes_registered_processor_with_reference_only_output() -> None:
    """A registered processor completes with a storage reference, not raw output."""
    asyncio.run(_complete_registered_processor())


async def _complete_registered_processor() -> None:
    job = _job()
    lease = JobLease(
        job.id,
        "worker",
        uuid4(),
        job.created_at,
        job.created_at,
        job.created_at + timedelta(seconds=60),
    )
    repository = AsyncMock()
    repository.acquire.return_value = (job, lease)
    repository.get_internal.return_value = job
    repository.latest_checkpoint.return_value = None
    resolver = AsyncMock()
    resolver.resolve_delegated.return_value = _context()
    processor = AsyncMock()
    processor.process.return_value = ProcessorResult("tactiqo://artifacts/result")
    runtime = JobWorkerRuntime(repository, resolver, {job.kind: processor}, worker_id="worker")

    assert await runtime.execute_once(job.kind)
    repository.finish_attempt.assert_awaited_once_with(
        lease,
        JobStatus.COMPLETED,
        stage="completed",
        outcome="completed",
        output_reference="tactiqo://artifacts/result",
    )


def test_runtime_fails_closed_when_delegated_authority_is_revoked() -> None:
    """Revoked delegated authority prevents processor execution."""
    asyncio.run(_reject_revoked_authority())


async def _reject_revoked_authority() -> None:
    job = _job()
    lease = JobLease(
        job.id,
        "worker",
        uuid4(),
        job.created_at,
        job.created_at,
        job.created_at + timedelta(seconds=60),
    )
    repository = AsyncMock()
    repository.acquire.return_value = (job, lease)
    repository.get_internal.return_value = job
    resolver = AsyncMock()
    resolver.resolve_delegated.return_value = None
    processor = AsyncMock()
    runtime = JobWorkerRuntime(repository, resolver, {job.kind: processor}, worker_id="worker")

    assert await runtime.execute_once(job.kind)
    processor.process.assert_not_awaited()
    repository.finish_attempt.assert_awaited_once_with(
        lease,
        JobStatus.FAILED,
        stage="authority_revoked",
        outcome="denied",
        failure_code="delegated_authority_revoked",
    )


def test_runtime_bounds_failure_with_retry_state() -> None:
    """Provider failures become sanitized bounded retry state."""
    asyncio.run(_schedule_bounded_retry())


async def _schedule_bounded_retry() -> None:
    job = _job()
    lease = JobLease(
        job.id,
        "worker",
        uuid4(),
        job.created_at,
        job.created_at,
        job.created_at + timedelta(seconds=60),
    )
    repository = AsyncMock()
    repository.acquire.return_value = (job, lease)
    repository.get_internal.return_value = job
    repository.latest_checkpoint.return_value = None
    repository.attempt_count.return_value = 1
    resolver = AsyncMock()
    resolver.resolve_delegated.return_value = _context()
    processor = AsyncMock()
    processor.process.side_effect = RuntimeError("secret provider detail")
    runtime = JobWorkerRuntime(repository, resolver, {job.kind: processor}, worker_id="worker")

    assert await runtime.execute_once(job.kind)
    call = repository.finish_attempt.await_args
    assert call.args[1] is JobStatus.RETRY_SCHEDULED
    assert call.kwargs["failure_code"] == "RuntimeError"
    assert "secret provider detail" not in str(call)
