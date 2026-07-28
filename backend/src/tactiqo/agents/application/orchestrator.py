"""Bounded LangGraph orchestration with durable events and approval interrupts."""

import asyncio
from dataclasses import asdict
from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID

from jsonschema import ValidationError, validate
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from tactiqo.agents.application.guardrails import InputGuardrails
from tactiqo.agents.application.ports import ModelProviderPort
from tactiqo.chat.application.ports import ChatRepository
from tactiqo.chat.domain.models import AgentEventType, MessageRole, RunStatus
from tactiqo.knowledge.application.ports import KnowledgeSearchPort
from tactiqo.knowledge.domain.models import KnowledgeResult
from tactiqo.shared.application.authorization import AuthorizationPort, ProtectedAction
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.policy import ToolPolicy
from tactiqo.tools.application.ports import ApprovalRepository, ToolAuditPort, ToolGateway
from tactiqo.tools.domain.models import (
    ApprovalStatus,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolRisk,
)


class AgentGraphState(TypedDict, total=False):
    """Serializable graph state persisted by the configured checkpointer."""

    run_id: str
    message: str
    context: dict[str, Any]
    tools_allowed: bool
    guardrail_reason: str
    evidence: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    response: str


class AgentOrchestrator:
    """Own the workflow while providers remain replaceable adapters."""

    def __init__(  # noqa: PLR0913 - explicit dependency injection is the composition contract
        self,
        *,
        chat_repository: ChatRepository,
        approval_repository: ApprovalRepository,
        authorization: AuthorizationPort,
        model_provider: ModelProviderPort,
        knowledge_search: KnowledgeSearchPort,
        tool_gateway: ToolGateway,
        tool_audit: ToolAuditPort,
        tool_policy: ToolPolicy,
        checkpointer: Any,  # noqa: ANN401 - LangGraph accepts multiple saver implementations
        maximum_tool_calls: int,
        timeout_seconds: float,
    ) -> None:
        """Compose replaceable providers and compile the bounded graph."""
        self._chat = chat_repository
        self._approvals = approval_repository
        self._authorization = authorization
        self._model = model_provider
        self._knowledge = knowledge_search
        self._tools = tool_gateway
        self._tool_audit = tool_audit
        self._tool_policy = tool_policy
        self._guardrails = InputGuardrails()
        self._maximum_tool_calls = maximum_tool_calls
        self._timeout_seconds = timeout_seconds
        self._graph = self._build_graph(checkpointer)

    async def start(
        self,
        run_id: UUID,
        message: str,
        context: ExecutionContext,
    ) -> None:
        """Start a new graph and translate all failures to safe run state."""
        await self._chat.update_run(run_id, RunStatus.RUNNING, "guardrails")
        await self._emit(run_id, AgentEventType.RUN_STARTED, {"step": "guardrails"})
        state: AgentGraphState = {
            "run_id": str(run_id),
            "message": message,
            "context": context.audit_metadata(),
            "tools_allowed": True,
            "evidence": [],
            "tools": [],
            "tool_calls": [],
            "tool_results": [],
        }
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._graph.ainvoke(state, self._config(run_id))
        except Exception as error:  # noqa: BLE001 - orchestration boundary redacts failures
            await self._fail(run_id, type(error).__name__)

    async def resume(self, run_id: UUID) -> None:
        """Resume a graph after an approval decision."""
        try:
            await self._chat.update_run(run_id, RunStatus.RUNNING, "tool_execution")
            async with asyncio.timeout(self._timeout_seconds):
                await self._graph.ainvoke(
                    Command(resume={"decision_recorded": True}),
                    self._config(run_id),
                )
        except Exception as error:  # noqa: BLE001 - orchestration boundary redacts failures
            await self._fail(run_id, type(error).__name__)

    def _build_graph(
        self,
        checkpointer: Any,  # noqa: ANN401 - LangGraph saver protocol is generic
    ) -> Any:  # noqa: ANN401 - LangGraph compiled graph has provider-specific generics
        graph = StateGraph(AgentGraphState)
        graph.add_node("guardrails", self._guardrail_node)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("execute_tool", self._tool_node)
        graph.add_node("respond", self._respond_node)
        graph.add_edge(START, "guardrails")
        graph.add_edge("guardrails", "retrieve")
        graph.add_edge("retrieve", "plan")
        graph.add_conditional_edges(
            "plan",
            self._next_after_plan,
            {"tool": "execute_tool", "respond": "respond"},
        )
        graph.add_edge("execute_tool", "respond")
        graph.add_edge("respond", END)
        return graph.compile(checkpointer=checkpointer)

    async def _guardrail_node(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        await self._check_cancelled(run_id)
        result = self._guardrails.evaluate(state["message"])
        await self._emit(
            run_id,
            AgentEventType.RUN_STEP,
            {"step": "guardrails", "status": result.reason_code},
        )
        if not result.allowed:
            msg = f"Input rejected by guardrail: {result.reason_code}"
            raise ValueError(msg)
        return {
            "tools_allowed": result.tool_execution_allowed,
            "guardrail_reason": result.reason_code,
        }

    async def _retrieve_node(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        await self._chat.update_run(run_id, RunStatus.RUNNING, "retrieval")
        await self._check_cancelled(run_id)
        context = self._context(state)
        decision = await self._authorization.authorize(context, ProtectedAction.RETRIEVE)
        evidence = (
            await self._knowledge.search(state["message"], context, limit=6)
            if decision.allowed
            else []
        )
        payload = [self._evidence_payload(item) for item in evidence]
        await self._emit(
            run_id,
            AgentEventType.RETRIEVAL_COMPLETED,
            {"count": len(payload), "citations": payload},
        )
        return {"evidence": payload}

    async def _plan_node(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        await self._chat.update_run(run_id, RunStatus.RUNNING, "planning")
        await self._check_cancelled(run_id)
        context = self._context(state)
        tools = await self._tools.list_tools() if state.get("tools_allowed", False) else []
        evidence = [self._evidence_from_payload(item) for item in state.get("evidence", [])]
        turn = await self._model.plan(state["message"], evidence, tools, context)
        calls = list(turn.tool_calls[: min(self._maximum_tool_calls, 1)])
        await self._emit(
            run_id,
            AgentEventType.RUN_STEP,
            {
                "step": "planning",
                "status": "tool_selected" if calls else "answer_selected",
            },
        )
        return {
            "tools": [self._tool_payload(tool) for tool in tools],
            "tool_calls": [asdict(call) for call in calls],
            "response": turn.text,
        }

    async def _tool_node(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        context = self._context(state)
        call = ToolCall(**state["tool_calls"][0])
        definitions = {
            item["name"]: ToolDefinition(
                name=item["name"],
                description=item["description"],
                input_schema=item["input_schema"],
                risk=ToolRisk(item["risk"]),
                server_label=item["server_label"],
            )
            for item in state.get("tools", [])
        }
        tool = definitions.get(call.name)
        if tool is None:
            return await self._rejected_tool(run_id, call, context, "tool_not_found")
        try:
            validate(instance=call.arguments, schema=tool.input_schema)
        except ValidationError:
            return await self._rejected_tool(run_id, call, context, "invalid_arguments")

        approval = await self._approvals.find_for_call(run_id, call.call_id)
        if approval is None:
            await self._emit(
                run_id,
                AgentEventType.TOOL_CALL,
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "risk": tool.risk.value,
                },
            )
            await self._tool_audit.record(
                run_id=run_id,
                tool_call_id=call.call_id,
                tool_name=call.name,
                phase="proposed",
                safe_payload={"risk": tool.risk.value},
                context=context,
            )
        if self._tool_policy.requires_approval(tool):
            if approval is None:
                approval = await self._approvals.create(
                    run_id,
                    call.call_id,
                    call.name,
                    call.arguments,
                    context,
                )
                await self._emit(
                    run_id,
                    AgentEventType.APPROVAL_REQUIRED,
                    {
                        "approval_id": str(approval.id),
                        "call_id": call.call_id,
                        "tool_name": call.name,
                        "arguments": call.arguments,
                    },
                )
            await self._chat.update_run(
                run_id,
                RunStatus.WAITING_APPROVAL,
                "awaiting_approval",
            )
            interrupt(
                {
                    "approval_id": str(approval.id),
                    "tool_name": call.name,
                }
            )
            approval = await self._approvals.get(approval.id)
            if approval is None or approval.status is not ApprovalStatus.APPROVED:
                return await self._rejected_tool(
                    run_id,
                    call,
                    context,
                    "rejected_by_user",
                )

        action = (
            ProtectedAction.TOOL_READ
            if tool.risk.value == "read_only"
            else ProtectedAction.TOOL_WRITE
        )
        policy = await self._authorization.authorize(context, action, call.name)
        if not policy.allowed:
            return await self._rejected_tool(run_id, call, context, "policy_denied")
        await self._chat.update_run(run_id, RunStatus.RUNNING, "tool_execution")
        raw_result = await self._tools.call_tool(call.name, call.arguments, context)
        result = ToolResult(
            call_id=call.call_id,
            name=raw_result.name,
            content=raw_result.content,
            is_error=raw_result.is_error,
        )
        await self._emit(
            run_id,
            AgentEventType.TOOL_RESULT,
            {
                "call_id": result.call_id,
                "name": result.name,
                "content": result.content,
                "is_error": result.is_error,
            },
        )
        await self._tool_audit.record(
            run_id=run_id,
            tool_call_id=call.call_id,
            tool_name=call.name,
            phase="completed",
            safe_payload={"is_error": result.is_error},
            context=context,
        )
        return {"tool_results": [asdict(result)]}

    async def _respond_node(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        await self._chat.update_run(run_id, RunStatus.RUNNING, "responding")
        await self._check_cancelled(run_id)
        context = self._context(state)
        evidence = [self._evidence_from_payload(item) for item in state.get("evidence", [])]
        results = [ToolResult(**item) for item in state.get("tool_results", [])]
        response = await self._model.answer(state["message"], evidence, results, context)
        for chunk in self._chunks(response):
            await self._emit(run_id, AgentEventType.MESSAGE_DELTA, {"delta": chunk})
            await asyncio.sleep(0.01)
        run = await self._chat.get_run(run_id)
        if run is None:
            msg = "Agent run disappeared before response persistence."
            raise LookupError(msg)
        message = await self._chat.add_message(
            run.conversation_id,
            MessageRole.ASSISTANT,
            response,
        )
        await self._emit(
            run_id,
            AgentEventType.MESSAGE_COMPLETED,
            {
                "message_id": str(message.id),
                "content": response,
                "citations": state.get("evidence", []),
            },
        )
        await self._chat.update_run(run_id, RunStatus.COMPLETED, "completed")
        await self._emit(run_id, AgentEventType.RUN_COMPLETED, {"status": "completed"})
        return {"response": response}

    @staticmethod
    def _next_after_plan(state: AgentGraphState) -> str:
        return "tool" if state.get("tool_calls") else "respond"

    async def _check_cancelled(self, run_id: UUID) -> None:
        run = await self._chat.get_run(run_id)
        if run is not None and run.cancel_requested:
            await self._chat.update_run(run_id, RunStatus.CANCELLED, "cancelled")
            await self._emit(run_id, AgentEventType.RUN_CANCELLED, {"status": "cancelled"})
            raise asyncio.CancelledError

    async def _fail(self, run_id: UUID, error_type: str) -> None:
        run = await self._chat.get_run(run_id)
        if run is not None and run.status is RunStatus.CANCELLED:
            return
        error_code = f"agent_{error_type.casefold()}"
        await self._chat.update_run(run_id, RunStatus.FAILED, "failed", error_code)
        await self._emit(
            run_id,
            AgentEventType.RUN_FAILED,
            {"error_code": error_code, "message": "The agent run failed safely."},
        )

    async def _emit(
        self,
        run_id: UUID,
        event_type: AgentEventType,
        payload: dict[str, Any],
    ) -> None:
        await self._chat.append_event(run_id, event_type.value, payload)

    @staticmethod
    def _config(run_id: UUID) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": str(run_id)}}

    @staticmethod
    def _context(state: AgentGraphState) -> ExecutionContext:
        raw = state["context"]
        return ExecutionContext(
            actor_id=str(raw["actor_id"]),
            organization_id=str(raw["organization_id"]),
            correlation_id=str(raw["correlation_id"]),
            classification_clearance=str(raw["classification_clearance"]),
            policy_version=str(raw["policy_version"]),
            organizational_unit_ids=tuple(raw.get("organizational_unit_ids", [])),
            project_ids=tuple(raw.get("project_ids", [])),
        )

    @staticmethod
    def _evidence_payload(item: KnowledgeResult) -> dict[str, Any]:
        return {
            "citation_id": item.citation_id,
            "document_id": str(item.document_id),
            "title": item.title,
            "content": item.content,
            "source_uri": item.source_uri,
            "locator": item.locator,
            "freshness": item.freshness.isoformat() if item.freshness else None,
            "score": item.score,
        }

    @staticmethod
    def _evidence_from_payload(item: dict[str, Any]) -> KnowledgeResult:
        freshness = datetime.fromisoformat(item["freshness"]) if item.get("freshness") else None
        return KnowledgeResult(
            citation_id=item["citation_id"],
            document_id=UUID(item["document_id"]),
            title=item["title"],
            content=item["content"],
            source_uri=item["source_uri"],
            locator=item["locator"],
            freshness=freshness,
            score=item.get("score"),
        )

    @staticmethod
    def _tool_payload(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "risk": tool.risk.value,
            "server_label": tool.server_label,
        }

    @staticmethod
    def _tool_error(call: ToolCall, code: str) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            content=f"Tool was not executed: {code}",
            is_error=True,
        )

    async def _rejected_tool(
        self,
        run_id: UUID,
        call: ToolCall,
        context: ExecutionContext,
        code: str,
    ) -> AgentGraphState:
        result = self._tool_error(call, code)
        await self._emit(
            run_id,
            AgentEventType.TOOL_RESULT,
            {"call_id": call.call_id, "name": call.name, "is_error": True, "code": code},
        )
        await self._tool_audit.record(
            run_id=run_id,
            tool_call_id=call.call_id,
            tool_name=call.name,
            phase="rejected",
            safe_payload={"code": code},
            context=context,
        )
        return {"tool_results": [asdict(result)]}

    @staticmethod
    def _chunks(value: str, size: int = 36) -> list[str]:
        return [value[index : index + size] for index in range(0, len(value), size)] or [""]
