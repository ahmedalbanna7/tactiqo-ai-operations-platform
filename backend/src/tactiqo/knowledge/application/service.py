"""Application use cases for document upload and listing."""

import hashlib
from pathlib import PurePath
from uuid import uuid4

from tactiqo.knowledge.application.ports import (
    IngestionPublisher,
    KnowledgeRepository,
    ObjectStorage,
)
from tactiqo.knowledge.domain.models import KnowledgeDocument
from tactiqo.shared.application.authorization import AuthorizationPort, ProtectedAction
from tactiqo.shared.domain.execution import ExecutionContext


class KnowledgeService:
    """Own validated upload flow while adapters own storage and processing."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        storage: ObjectStorage,
        publisher: IngestionPublisher,
        authorization: AuthorizationPort,
        maximum_bytes: int,
    ) -> None:
        """Configure storage, queueing, policy, and upload limits."""
        self._repository = repository
        self._storage = storage
        self._publisher = publisher
        self._authorization = authorization
        self._maximum_bytes = maximum_bytes

    async def upload(
        self,
        *,
        name: str,
        content_type: str,
        content: bytes,
        project_id: str | None,
        context: ExecutionContext,
    ) -> KnowledgeDocument:
        """Store an original, create canonical truth, and enqueue parsing."""
        decision = await self._authorization.authorize(
            context,
            ProtectedAction.DOCUMENT_UPLOAD,
        )
        if not decision.allowed:
            msg = f"Policy denied upload: {decision.reason_code}"
            raise PermissionError(msg)
        if not content or len(content) > self._maximum_bytes:
            msg = "Document is empty or exceeds the configured upload limit."
            raise ValueError(msg)
        safe_name = PurePath(name).name.strip()[:255] or "document"
        storage_key = f"{context.organization_id}/{uuid4().hex}/{safe_name}"
        checksum = hashlib.sha256(content).hexdigest()
        await self._storage.put(storage_key, content, content_type)
        document = await self._repository.create_document(
            name=safe_name,
            content_type=content_type,
            storage_key=storage_key,
            checksum_sha256=checksum,
            context=context,
            project_id=project_id,
        )
        await self._publisher.publish(document.id)
        return document

    async def list_documents(
        self,
        context: ExecutionContext,
    ) -> list[KnowledgeDocument]:
        """List document processing states within organization scope."""
        return await self._repository.list_documents(context)
