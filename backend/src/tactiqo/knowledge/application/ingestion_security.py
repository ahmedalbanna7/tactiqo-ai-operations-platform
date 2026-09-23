"""Fail-closed upload validation before object storage and parsing."""

import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

_OOXML_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_TEXT_SUFFIXES = {".txt", ".md", ".csv"}


class UnsafeDocumentError(ValueError):
    """Upload failed a stable, user-safe document boundary check."""


@dataclass(frozen=True, slots=True)
class DocumentUploadValidator:
    """Validate extension/signature and bounded OOXML archive structure."""

    maximum_archive_entries: int = 10_000
    maximum_expansion_ratio: int = 100

    def validate(self, name: str, content_type: str, content: bytes) -> None:
        """Reject unsupported, spoofed, encrypted, or suspicious uploads."""
        suffix = PurePath(name).suffix.lower()
        if suffix == ".pdf":
            self._require(content.startswith(b"%PDF-"), "document_signature_mismatch")
            return
        if suffix in _OOXML_TYPES:
            self._require(content_type == _OOXML_TYPES[suffix], "document_mime_mismatch")
            self._validate_archive(content)
            return
        if suffix in _TEXT_SUFFIXES:
            self._require(b"\x00" not in content[:8192], "binary_content_not_allowed")
            return
        message = "document_type_not_allowed"
        raise UnsafeDocumentError(message)

    def _validate_archive(self, content: bytes) -> None:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                self._require(
                    len(entries) <= self.maximum_archive_entries, "archive_too_many_entries"
                )
                expanded = sum(entry.file_size for entry in entries)
                compressed = max(1, sum(entry.compress_size for entry in entries))
                self._require(
                    expanded <= compressed * self.maximum_expansion_ratio,
                    "archive_expansion_limit",
                )
                self._require(
                    not any(entry.flag_bits & 0x1 for entry in entries), "encrypted_archive"
                )
                self._require(
                    not any(".." in PurePath(entry.filename).parts for entry in entries),
                    "archive_path_traversal",
                )
        except zipfile.BadZipFile as error:
            message = "document_signature_mismatch"
            raise UnsafeDocumentError(message) from error

    @staticmethod
    def _require(condition: bool, code: str) -> None:  # noqa: FBT001
        if not condition:
            raise UnsafeDocumentError(code)
