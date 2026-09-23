"""F9 company-knowledge elevation must be explicit and tenant-safe."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tactiqo.knowledge.application.service import KnowledgeService
from tactiqo.knowledge.infrastructure.repositories import SqlAlchemyKnowledgeRepository
from tactiqo.shared.domain.execution import ExecutionContext


def _context(*roles: str) -> ExecutionContext:
    return ExecutionContext(
        actor_id=str(uuid4()),
        organization_id="tenant-a",
        correlation_id="f9-test",
        classification_clearance="internal",
        policy_version="v1",
        role_codes=roles,
    )


def _service() -> tuple[KnowledgeService, AsyncMock]:
    repository = AsyncMock()
    service = KnowledgeService(repository, AsyncMock(), AsyncMock(), AsyncMock(), 1024)
    return service, repository


@pytest.mark.anyio
async def test_employee_cannot_promote_or_upload_company_knowledge() -> None:
    """An employee is rejected before any storage or metadata lookup."""
    service, repository = _service()
    context = _context("employee")
    with pytest.raises(PermissionError, match="company_knowledge_requires_admin"):
        await service.promote(uuid4(), "source.txt", context)
    repository.get_document.assert_not_awaited()
    with pytest.raises(PermissionError, match="company_knowledge_requires_admin"):
        await service.upload(
            name="source.txt", content_type="text/plain", content=b"safe",
            project_id=None, context=context, owner_scope="organization",
        )
    repository.create_document.assert_not_awaited()


@pytest.mark.anyio
async def test_promotion_requires_owned_document_and_exact_confirmation() -> None:
    """Admin role alone never promotes a foreign or misconfirmed source."""
    service, repository = _service()
    context = _context("owner")
    document_id = uuid4()
    repository.get_document.return_value = SimpleNamespace(
        name="source.txt", actor_id=str(uuid4())
    )
    assert await service.promote(document_id, "source.txt", context) is None
    repository.promote_document.assert_not_awaited()

    repository.get_document.return_value = SimpleNamespace(
        name="source.txt", actor_id=context.actor_id
    )
    with pytest.raises(ValueError, match="knowledge_promotion_confirmation_mismatch"):
        await service.promote(document_id, "wrong.txt", context)
    repository.promote_document.assert_not_awaited()

    repository.promote_document.return_value = repository.get_document.return_value
    assert await service.promote(document_id, "source.txt", context) is not None
    repository.promote_document.assert_awaited_once_with(document_id, context)


def test_personal_scope_does_not_inherit_project_membership() -> None:
    """A shared project alone must not turn a personal upload into shared knowledge."""
    context = _context("employee")
    expression = SqlAlchemyKnowledgeRepository._document_scope(context)  # noqa: SLF001
    sql = str(expression.compile(compile_kwargs={"literal_binds": True}))
    assert "owner_scope" in sql
    assert "actor_id" in sql
    assert "project_id" not in sql
