"""SQLAlchemy mappings for canonical documents and parsed elements."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
