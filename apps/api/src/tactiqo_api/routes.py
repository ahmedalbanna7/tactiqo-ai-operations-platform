"""Thin HTTP and SSE adapters for system and F1 application use cases."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.domain.health import HealthStatus
from tactiqo.tools.domain.models import ApprovalStatus
from tactiqo_api.middleware import get_correlation_id
from tactiqo_api.schemas import (
    AgentRunResponse,
    ApprovalDecisionRequest,
    ApprovalResponse,
    ComponentHealthResponse,
    ConversationResponse,
    CreateConversationRequest,
    DocumentResponse,
    HealthResponse,
    MessageResponse,
    SendMessageRequest,
    ServiceInfoResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tactiqo.chat.application.service import ChatService
    from tactiqo.chat.domain.models import AgentRun, Conversation, Message
    from tactiqo.knowledge.application.service import KnowledgeService
    from tactiqo.knowledge.domain.models import KnowledgeDocument
    from tactiqo.shared.application.health import ReadinessService
    from tactiqo.shared.infrastructure.settings import Settings
    from tactiqo.tools.application.service import ApprovalService
    from tactiqo.tools.domain.models import ApprovalRequest

router = APIRouter(tags=["system"])
api_router = APIRouter(prefix="/api/v1")


def _settings(request: Request) -> Settings:
    return cast("Settings", request.app.state.settings)


def _context(request: Request) -> ExecutionContext:
    settings = _settings(request)
    if not settings.local_development_context_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Identity provider not configured."
        )
    return ExecutionContext(
        actor_id=settings.local_actor_id,
        organization_id=settings.local_organization_id,
        correlation_id=get_correlation_id() or str(uuid4()),
        classification_clearance=settings.local_classification,
        policy_version=settings.local_policy_version,
    )


def _chat(request: Request) -> ChatService:
    return cast("ChatService", request.app.state.chat_service)


def _approvals(request: Request) -> ApprovalService:
    return cast("ApprovalService", request.app.state.approval_service)


def _knowledge(request: Request) -> KnowledgeService:
    return cast("KnowledgeService", request.app.state.knowledge_service)


@router.get("/")
async def service_info(request: Request) -> ServiceInfoResponse:
    """Return public service identity metadata."""
    settings = _settings(request)
    return ServiceInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get("/health/live")
async def liveness(request: Request) -> HealthResponse:
    """Return process liveness without dependency checks."""
    settings = _settings(request)
    return HealthResponse(
        status=HealthStatus.HEALTHY.value,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get(
    "/health/ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def readiness(request: Request, response: Response) -> HealthResponse:
    """Return fail-closed dependency readiness."""
    settings = _settings(request)
    service: ReadinessService = request.app.state.readiness_service
    health = await service.evaluate()
    if health.status is HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=health.status.value,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        components=[
            ComponentHealthResponse(
                name=component.name,
                status=component.status.value,
                detail=component.detail,
            )
            for component in health.components
        ],
    )


@api_router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: CreateConversationRequest,
    request: Request,
) -> ConversationResponse:
    """Create a conversation in the local execution scope."""
    conversation = await _chat(request).create_conversation(_context(request), payload.title)
    return _conversation_response(conversation)


@api_router.get("/conversations")
async def list_conversations(request: Request) -> list[ConversationResponse]:
    """List visible conversations newest first."""
    conversations = await _chat(request).list_conversations(_context(request))
    return [_conversation_response(item) for item in conversations]


@api_router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: UUID, request: Request) -> list[MessageResponse]:
    """List ordered messages for a visible conversation."""
    messages = await _chat(request).list_messages(_context(request), conversation_id)
    if messages is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return [_message_response(item) for item in messages]


@api_router.post(
    "/conversations/{conversation_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    request: Request,
) -> AgentRunResponse:
    """Persist a user turn and start a bounded run."""
    run = await _chat(request).send_message(
        _context(request),
        conversation_id,
        payload.content,
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return _run_response(run)


@api_router.get("/runs/{run_id}")
async def get_run(run_id: UUID, request: Request) -> AgentRunResponse:
    """Return current state for a visible run."""
    run = await _chat(request).get_run(_context(request), run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return _run_response(run)


@api_router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: UUID, request: Request) -> AgentRunResponse:
    """Request cancellation of a visible run."""
    run = await _chat(request).cancel(_context(request), run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return _run_response(run)


@api_router.get("/runs/{run_id}/events")
async def stream_events(run_id: UUID, request: Request, after: int = 0) -> StreamingResponse:
    """Stream ordered resumable events until the run becomes terminal."""
    context = _context(request)
    if await _chat(request).get_run(context, run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")

    async def events() -> AsyncIterator[str]:
        cursor = after
        while True:
            batch = await _chat(request).list_events(context, run_id, cursor)
            if batch is None:
                return
            for event in batch:
                cursor = event.sequence
                data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {event.sequence}\nevent: {event.event_type.value}\ndata: {data}\n\n"
            run = await _chat(request).get_run(context, run_id)
            if run is None or (run.status.terminal and not batch):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(_settings(request).agent_event_poll_seconds)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    request: Request,
) -> ApprovalResponse:
    """Record a scoped immutable human approval decision."""
    approval = await _approvals(request).decide(
        approval_id,
        ApprovalStatus(payload.decision),
        _context(request),
    )
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found.")
    return _approval_response(approval)


@api_router.post(
    "/knowledge/documents",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    project_id: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    """Store an original document and enqueue asynchronous parsing."""
    settings = _settings(request)
    content = await file.read(settings.max_upload_bytes + 1)
    try:
        document = await _knowledge(request).upload(
            name=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            project_id=project_id,
            context=_context(request),
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(error)) from error
    return _document_response(document)


@api_router.get("/knowledge/documents")
async def list_documents(request: Request) -> list[DocumentResponse]:
    """List visible knowledge documents and processing status."""
    documents = await _knowledge(request).list_documents(_context(request))
    return [_document_response(item) for item in documents]


def _conversation_response(item: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=item.id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _message_response(item: Message) -> MessageResponse:
    return MessageResponse(
        id=item.id,
        role=item.role.value,
        content=item.content,
        created_at=item.created_at,
    )


def _run_response(item: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=item.id,
        conversation_id=item.conversation_id,
        status=item.status.value,
        current_step=item.current_step,
        cancel_requested=item.cancel_requested,
        error_code=item.error_code,
        created_at=item.created_at,
        updated_at=item.updated_at,
        completed_at=item.completed_at,
    )


def _approval_response(item: ApprovalRequest) -> ApprovalResponse:
    return ApprovalResponse(
        id=item.id,
        run_id=item.run_id,
        tool_name=item.tool_name,
        arguments=item.arguments,
        status=item.status.value,
        created_at=item.created_at,
        decided_at=item.decided_at,
    )


def _document_response(item: KnowledgeDocument) -> DocumentResponse:
    return DocumentResponse(
        id=item.id,
        name=item.name,
        content_type=item.content_type,
        source_uri=item.source_uri,
        status=item.status.value,
        project_id=item.project_id,
        parser_name=item.parser_name,
        error_code=item.error_code,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
