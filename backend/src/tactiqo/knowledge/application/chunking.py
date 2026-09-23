"""Deterministic structure-preserving multilingual chunking."""

from dataclasses import dataclass

from tactiqo.knowledge.domain.models import CanonicalDocumentElement


@dataclass(frozen=True, slots=True)
class ChunkCandidate:
    """Bounded text slice retaining its canonical source locator."""

    text: str
    locator: dict[str, object]


@dataclass(frozen=True, slots=True)
class StructureAwareChunker:
    """Split oversized elements at whitespace with bounded overlap."""

    maximum_characters: int = 1800
    overlap_characters: int = 180

    def chunk(self, elements: list[CanonicalDocumentElement]) -> list[ChunkCandidate]:
        """Return ordered chunks without crossing element/page/table boundaries."""
        chunks: list[ChunkCandidate] = []
        for element in elements:
            text = element.text.strip()
            start = 0
            part = 1
            while text[start:]:
                end = min(len(text), start + self.maximum_characters)
                if end < len(text):
                    boundary = text.rfind(" ", start, end)
                    if boundary > start:
                        end = boundary
                piece = text[start:end].strip()
                if piece:
                    locator = dict(element.locator)
                    locator.update({"element": element.ordinal, "part": part})
                    chunks.append(ChunkCandidate(piece, locator))
                if end >= len(text):
                    break
                start = max(start + 1, end - self.overlap_characters)
                part += 1
        return chunks
