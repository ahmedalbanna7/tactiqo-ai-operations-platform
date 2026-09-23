"""F5 job submission and scoped operations use cases."""

from uuid import UUID

from tactiqo.agents.domain.planning import ExecutionPlan
from tactiqo.jobs.application.ports import JobPublisher, JobRepository
from tactiqo.jobs.domain.models import Job, JobKind, JobRisk
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.work_envelope import WorkEnvelopeSigner


class JobService:
    """Create reference-only jobs and expose only their originating scope."""

    def __init__(
        self,
        repository: JobRepository,
        publisher: JobPublisher,
        signer: WorkEnvelopeSigner,
    ) -> None:
        """Configure durable truth, transport, and delegated authority signing."""
        self._repository = repository
        self._publisher = publisher
        self._signer = signer

    async def dispatch(self, plan: ExecutionPlan, context: ExecutionContext) -> str:
        """Persist before publish and deduplicate one executable plan step."""
        step = plan.steps[0]
        kind = self._kind(plan, step.agent_code)
        risk = JobRisk(step.risk)
        job, created = await self._repository.create(
            run_id=plan.run_id,
            plan_id=plan.id,
            step_id=step.id,
            kind=kind,
            risk=risk,
            idempotency_key=step.idempotency_key,
            input_reference=f"tactiqo://runs/{plan.run_id}/input",
            context=context,
            maximum_attempts=plan.budget.maximum_retries + 1,
        )
        if created:
            await self._publisher.publish(job, self._signer.sign(context))
        return str(job.id)

    async def list(self, context: ExecutionContext) -> list[Job]:
        """List actor-owned jobs in the current tenant."""
        return await self._repository.list(context)

    async def get(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Return one actor-owned job without disclosing cross-scope existence."""
        return await self._repository.get(job_id, context)

    async def cancel(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Request cooperative cancellation in exact actor and tenant scope."""
        return await self._repository.request_cancel(job_id, context)

    async def retry(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Explicitly requeue visible failed work and publish its reference again."""
        job = await self._repository.retry(job_id, context)
        if job is not None:
            await self._publisher.publish(job, self._signer.sign(context))
        return job

    async def metrics(self, context: ExecutionContext) -> dict[str, int]:
        """Return scope-safe job counts for the operations UI."""
        return await self._repository.status_counts(context)

    @staticmethod
    def _kind(plan: ExecutionPlan, agent_code: str) -> JobKind:
        if plan.estimate.media_count:
            return JobKind.MEDIA
        if agent_code == "data_analytics":
            return JobKind.REPORT_BI
        if agent_code == "risk_compliance":
            return JobKind.RISK_REVIEW
        if agent_code in {"automation_integrations", "planner"}:
            return JobKind.INTEGRATION_AUTOMATION
        return JobKind.DOCUMENT_OCR
