"""Document parsing boundary independent of Unstructured-specific objects."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DocumentParseRequest:
    """Describe an authorized, versioned object-storage document to parse."""

    document_id: str
    document_version_id: str
    object_reference: str
    media_type: str
    checksum: str
    strategy: str
    language_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CanonicalDocumentElement:
    """Represent one parser-independent element with stable provenance."""

    element_id: str
    document_version_id: str
    element_type: str
    text: str
    source_locator: str
    parser_name: str
    parser_version: str
    strategy: str
    quality_flags: tuple[str, ...]


class DocumentParser(Protocol):
    """Normalize document bytes into canonical evidence elements."""

    async def parse(
        self,
        request: DocumentParseRequest,
    ) -> tuple[CanonicalDocumentElement, ...]:
        """Parse one authorized document version idempotently.

        Args:
            request: Stable file reference and parsing policy.

        Returns:
            Parser-independent canonical elements with provenance.

        """
        ...
