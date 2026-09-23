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
    REVOKED = "revoked"


class KnowledgeSourceType(StrEnum):
    """Provider-neutral origins synchronized into canonical knowledge."""

    UPLOAD = "upload"
    JIRA = "jira"
    SLACK = "slack"
    CONFLUENCE = "confluence"
    DRIVE = "drive"
    SHAREPOINT = "sharepoint"


class SourceStatus(StrEnum):
    """Explicit source synchronization lifecycle."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    REVOKED = "revoked"


class KnowledgeDomain(StrEnum):
    """Business domain used for metadata filtering before retrieval."""

    GENERAL = "general"
    PROJECT = "project"
    HR = "hr"
    FINANCE = "finance"
    IT = "it"
    LEGAL = "legal"
    OPERATIONS = "operations"


class KnowledgePurpose(StrEnum):
    """Intended retrieval treatment selected by an authorized uploader."""

    AUTHORITATIVE = "authoritative"
    RESEARCH = "research"
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    """Tenant-owned logical source without provider credentials."""

    id: UUID
    organization_id: str
    source_type: KnowledgeSourceType
    name: str
    connection_id: UUID | None
    status: SourceStatus
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    """Immutable content version and retention/lineage state."""

    id: UUID
    document_id: UUID
    version_number: int
    content_hash: str
    supersedes_version_id: UUID | None
    parser_name: str | None
    parser_version: str | None
    retention_until: datetime | None
    legal_hold: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """Normalized retrieval unit with exact locator and classification."""

    id: UUID
    document_id: UUID
    version_id: UUID
    ordinal: int
    text: str
    normalized_text: str
    language: str
    token_count: int
    locator: dict[str, Any]
    classification: str


@dataclass(frozen=True, slots=True)
class AclSnapshot:
    """Immutable source ACL evidence captured before indexing."""

    id: UUID
    document_id: UUID
    version_id: UUID
    organization_id: str
    user_ids: tuple[str, ...]
    department_ids: tuple[str, ...]
    team_ids: tuple[str, ...]
    project_ids: tuple[str, ...]
    policy_version: str
    source_acl_hash: str
    captured_at: datetime


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
    domain: KnowledgeDomain = KnowledgeDomain.GENERAL
    purpose: KnowledgePurpose = KnowledgePurpose.RESEARCH
    owner_scope: str = "personal"


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
