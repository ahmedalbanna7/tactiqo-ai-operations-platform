"""SQLAlchemy mappings for canonical documents and parsed elements."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tactiqo.chat.infrastructure.tables import utc_now
from tactiqo.shared.infrastructure.database import Base


class KnowledgeDocumentRow(Base):
    """Persistence model for document identity, scope, and processing state."""

    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    source_uri: Mapped[str] = mapped_column(String(512), unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[str] = mapped_column(String(128))
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    classification: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(32), default="general", index=True)
    purpose: Mapped[str] = mapped_column(String(32), default="research", index=True)
    owner_scope: Mapped[str] = mapped_column(String(24), default="personal", index=True)
    parser_name: Mapped[str | None] = mapped_column(String(96), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeElementRow(Base):
    """Persistence model for normalized Unstructured/native elements."""

    __tablename__ = "knowledge_document_elements"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_knowledge_element_ordinal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    element_type: Mapped[str] = mapped_column(String(96))
    text: Mapped[str] = mapped_column(Text)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON)


class KnowledgeSourceRow(Base):
    """Tenant-owned logical source and synchronization lifecycle."""

    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_type", "name", name="uq_knowledge_source"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    connection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), index=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DocumentVersionRow(Base):
    """Immutable document content version and lineage."""

    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        UniqueConstraint("document_id", "content_hash", name="uq_document_content_hash"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_document_versions.id", ondelete="SET NULL"), nullable=True
    )
    parser_name: Mapped[str | None] = mapped_column(String(96), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeChunkRow(Base):
    """Normalized retrieval unit; vector indexes are added in F7.3."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("version_id", "ordinal", name="uq_knowledge_chunk_ordinal"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), index=True)
    token_count: Mapped[int] = mapped_column(Integer)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON)
    classification: Mapped[str] = mapped_column(String(64), index=True)
    security_signals: Mapped[list[str]] = mapped_column(JSON, default=list)


class KnowledgeAclSnapshotRow(Base):
    """Immutable ACL evidence attached before chunk indexing."""

    __tablename__ = "knowledge_acl_snapshots"
    __table_args__ = (UniqueConstraint("version_id", name="uq_acl_snapshot_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    organization_access: Mapped[bool] = mapped_column(Boolean, default=False)
    user_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    department_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    team_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    project_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy_version: Mapped[str] = mapped_column(String(64))
    source_acl_hash: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceSyncCheckpointRow(Base):
    """Opaque cursor for idempotent resumable source synchronization."""

    __tablename__ = "knowledge_source_sync_checkpoints"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), unique=True
    )
    cursor_reference: Mapped[str] = mapped_column(String(512))
    last_item_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    synchronized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeEmbeddingSpaceRow(Base):
    """Immutable tenant-scoped identity for one embedding model space."""

    __tablename__ = "knowledge_embedding_spaces"
    __table_args__ = (
        UniqueConstraint("organization_id", "space_key", name="uq_knowledge_embedding_space"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    space_key: Mapped[str] = mapped_column(String(96))
    model: Mapped[str] = mapped_column(String(255))
    dimensions: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
