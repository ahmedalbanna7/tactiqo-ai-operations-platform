"""Application use cases for scoped human approval decisions."""

from uuid import UUID

from tactiqo.agents.application.supervisor import AgentTaskSupervisor
from tactiqo.chat.application.ports import ChatRepository
from tactiqo.chat.domain.models import AgentEventType
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.ports import ApprovalRepository
from tactiqo.tools.domain.models import ApprovalRequest, ApprovalStatus


class ApprovalService:
    """Authorize approval visibility and resume interrupted graphs."""

    def __init__(
        self,
        approvals: ApprovalRepository,
        chat: ChatRepository,
        supervisor: AgentTaskSupervisor,
    ) -> None:
        """Configure approval persistence and graph resumption."""
        self._approvals = approvals
        self._chat = chat
        self._supervisor = supervisor

    async def decide(
        self,
        approval_id: UUID,
        decision: ApprovalStatus,
        context: ExecutionContext,
    ) -> ApprovalRequest | None:
        """Apply an immutable scoped decision and resume the run once."""
        existing = await self._approvals.get(approval_id)
        if existing is None or not self._visible(existing, context):
            return None
        if existing.status is not ApprovalStatus.PENDING:
            return existing
        updated = await self._approvals.decide(approval_id, decision, context.actor_id)
        if updated is None:
            return None
        await self._chat.append_event(
            updated.run_id,
            AgentEventType.APPROVAL_DECIDED.value,
            {
                "approval_id": str(updated.id),
                "status": updated.status.value,
                "decided_by": context.actor_id,
            },
        )
        self._supervisor.resume(updated.run_id)
        return updated

    @staticmethod
    def _visible(approval: ApprovalRequest, context: ExecutionContext) -> bool:
        return (
            approval.organization_id == context.organization_id
            and approval.actor_id == context.actor_id
        )
