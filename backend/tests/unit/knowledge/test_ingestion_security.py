"""F7 upload security and structure-aware chunking tests."""

from uuid import uuid4

import pytest

from tactiqo.knowledge.application.chunking import StructureAwareChunker
from tactiqo.knowledge.application.ingestion_security import (
    DocumentUploadValidator,
    UnsafeDocumentError,
)
from tactiqo.knowledge.domain.models import CanonicalDocumentElement


def test_pdf_extension_requires_pdf_signature() -> None:
    """Renaming arbitrary content to PDF cannot reach storage or parser."""
    with pytest.raises(UnsafeDocumentError, match="document_signature_mismatch"):
        DocumentUploadValidator().validate("report.pdf", "application/pdf", b"not a pdf")


def test_text_rejects_embedded_binary_content() -> None:
    """Text paths reject binary payloads before permissive decoding."""
    with pytest.raises(UnsafeDocumentError, match="binary_content_not_allowed"):
        DocumentUploadValidator().validate("notes.txt", "text/plain", b"safe\x00payload")


def test_chunker_preserves_locator_and_bounds_large_element() -> None:
    """Oversized text is sliced without losing exact element provenance."""
    maximum = 80
    page = 3
    ordinal = 7
    element = CanonicalDocumentElement(
        uuid4(), uuid4(), ordinal, "NarrativeText", "word " * 100, {"page": page}
    )
    chunks = StructureAwareChunker(maximum_characters=maximum, overlap_characters=10).chunk(
        [element]
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= maximum for chunk in chunks)
    assert all(
        chunk.locator["page"] == page and chunk.locator["element"] == ordinal for chunk in chunks
    )
