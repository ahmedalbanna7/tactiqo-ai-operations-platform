"""Application use cases for document upload and listing."""

import hashlib
from pathlib import PurePath
from uuid import UUID, uuid4

from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.knowledge.application.ingestion_security import DocumentUploadValidator
from tactiqo.knowledge.application.ports import (
    IngestionPublisher,
    KnowledgeRepository,
    ObjectStorage,
)
from tactiqo.knowledge.domain.models import (
    KnowledgeDocument,
    KnowledgeDomain,
    KnowledgePurpose,
    KnowledgeResult,
)
from tactiqo.shared.application.authorization import AuthorizationPort, ProtectedAction
from tactiqo.shared.domain.execution import ExecutionContext


class KnowledgeService:
    """Own validated upload flow while adapters own storage and processing."""

    def __init__(  # noqa: PLR0913 - explicit application dependencies
        self,
        repository: KnowledgeRepository,
        storage: ObjectStorage,
        publisher: IngestionPublisher,
        authorization: AuthorizationPort,
        maximum_bytes: int,
        validator: DocumentUploadValidator | None = None,
    ) -> None:
        """Configure storage, queueing, policy, and upload limits."""
        self._repository = repository
        self._storage = storage
        self._publisher = publisher
        self._authorization = authorization
        self._maximum_bytes = maximum_bytes
        self._validator = validator or DocumentUploadValidator()

    async def upload(  # noqa: PLR0913 - explicit governed metadata contract
        self,
        *,
        name: str,
        content_type: str,
        content: bytes,
        project_id: str | None,
        context: ExecutionContext,
        domain: KnowledgeDomain = KnowledgeDomain.GENERAL,
        purpose: KnowledgePurpose = KnowledgePurpose.RESEARCH,
        owner_scope: str = "personal",
    ) -> KnowledgeDocument:
        """Store an original, create canonical truth, and enqueue parsing."""
        decision = await self._authorization.authorize(
            context,
            ProtectedAction.DOCUMENT_UPLOAD,
        )
        if not decision.allowed:
            msg = f"Policy denied upload: {decision.reason_code}"
            raise PermissionError(msg)
        if owner_scope not in {"personal", "organization"}:
            message = "invalid_knowledge_owner_scope"
            raise ValueError(message)
        if owner_scope == "organization" and not self._is_admin(context):
            message = "company_knowledge_requires_admin"
            raise PermissionError(message)
        if not content or len(content) > self._maximum_bytes:
            msg = "Document is empty or exceeds the configured upload limit."
            raise ValueError(msg)
        safe_name = PurePath(name).name.strip()[:255] or "document"
        self._validator.validate(safe_name, content_type, content)
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
            domain=domain.value,
            purpose=purpose.value,
            owner_scope=owner_scope,
        )
        await self._publisher.publish(document.id, context)
        return document

    async def list_documents(
        self,
        context: ExecutionContext,
        owner_scope: str | None = None,
    ) -> list[KnowledgeDocument]:
        """List document processing states within organization scope."""
        if owner_scope not in {None, "personal", "organization"}:
            message = "invalid_knowledge_owner_scope"
            raise ValueError(message)
        return await self._repository.list_documents(context, owner_scope=owner_scope)

    async def promote(
        self, document_id: UUID, confirmation_name: str, context: ExecutionContext
    ) -> KnowledgeDocument | None:
        """Broaden a personally owned source after explicit admin confirmation."""
        if not self._is_admin(context):
            message = "company_knowledge_requires_admin"
            raise PermissionError(message)
        document = await self._repository.get_document(document_id, context)
        if document is None or document.actor_id != context.actor_id:
            return None
        if confirmation_name != document.name:
            message = "knowledge_promotion_confirmation_mismatch"
            raise ValueError(message)
        return await self._repository.promote_document(document_id, context)

    @staticmethod
    def _is_admin(context: ExecutionContext) -> bool:
        admin_roles = {
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }
        return bool(admin_roles.intersection(context.role_codes))

    async def preview(
        self,
        document_id: UUID,
        chunk_ordinal: int,
        radius: int,
        context: ExecutionContext,
    ) -> list[KnowledgeResult]:
        """Return a bounded preview after repository-level ACL revalidation."""
        return await self._repository.preview(document_id, chunk_ordinal, radius, context)

    async def revoke(
        self,
        document_id: UUID,
        confirmation_name: str,
        context: ExecutionContext,
    ) -> KnowledgeDocument | None:
        """Withdraw one owned document after explicit name confirmation."""
        decision = await self._authorization.authorize(
            context, ProtectedAction.DOCUMENT_REVOKE, str(document_id)
        )
        if not decision.allowed:
            message = f"Policy denied document revocation: {decision.reason_code}"
            raise PermissionError(message)
        document = await self._repository.get_document(document_id, context)
        if document is None:
            return None
        admin_roles = {
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }
        if document.actor_id != context.actor_id and not admin_roles.intersection(
            context.role_codes
        ):
            return None
        if confirmation_name != document.name:
            message = "document_name_confirmation_mismatch"
            raise ValueError(message)
        return await self._repository.revoke_document(document_id, context)
