"""Canonical documents, elements, and retrieval evidence."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class DocumentStatus(StrEnum):
    """Durable document processing lifecycle."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Platform-owned canonical document identity and scope."""

    id: UUID
    name: str
    content_type: str
    storage_key: str
    source_uri: str
    checksum_sha256: str
    status: DocumentStatus
    actor_id: str
    organization_id: str
    classification: str
    project_id: str | None
    parser_name: str | None
    parser_version: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CanonicalDocumentElement:
    """Provider-neutral parsed element with exact source provenance."""

    id: UUID
    document_id: UUID
    ordinal: int
    element_type: str
    text: str
    locator: dict[str, Any]


@dataclass(frozen=True, slots=True)
class KnowledgeResult:
    """Authorized evidence returned to the orchestration layer."""

    citation_id: str
    document_id: UUID
    title: str
    content: str
    source_uri: str
    locator: dict[str, Any]
    freshness: datetime | None
    score: float | None = None
