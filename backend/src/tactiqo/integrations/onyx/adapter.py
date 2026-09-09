"""Typed Onyx ingestion and search adapter using only supported HTTP APIs."""

from collections.abc import Sequence

import httpx

from tactiqo.knowledge.application.content_security import DocumentContentSecurityScanner
from tactiqo.knowledge.application.ports import KnowledgeRepository
from tactiqo.knowledge.domain.models import (
    CanonicalDocumentElement,
    KnowledgeDocument,
    KnowledgeResult,
)
from tactiqo.shared.domain.execution import ExecutionContext


class OnyxAdapter:
    """Use Onyx as a derived index while platform PostgreSQL remains authoritative."""

    def __init__(
        self,
        base_url: str,
        token: str,
        repository: KnowledgeRepository,
        timeout_seconds: float = 30,
        content_security: DocumentContentSecurityScanner | None = None,
    ) -> None:
        """Configure supported Onyx endpoints and platform scope validation."""
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._repository = repository
        self._timeout_seconds = timeout_seconds
        self._content_security = content_security or DocumentContentSecurityScanner()

    async def index(
        self,
        document: KnowledgeDocument,
        elements: Sequence[CanonicalDocumentElement],
    ) -> None:
        """Upsert canonical elements through Onyx's ingestion API."""
        sections = [
            {
                "type": "text",
                "text": element.text,
                "link": document.source_uri,
                "heading": element.locator.get("heading"),
            }
            for element in elements
            if element.text.strip()
        ]
        payload = {
            "document": {
                "id": str(document.id),
                "sections": sections,
                "source": "ingestion_api",
                "semantic_identifier": document.name,
                "title": document.name,
                "metadata": {
                    "tactiqo_document_id": str(document.id),
                    "organization_id": document.organization_id,
                    "classification": document.classification,
                    "project_id": document.project_id or "",
                    "checksum_sha256": document.checksum_sha256,
                },
            }
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/api/onyx-api/ingestion",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()

    async def search(
        self,
        query: str,
        context: ExecutionContext,
        limit: int = 6,
    ) -> list[KnowledgeResult]:
        """Search Onyx then revalidate every citation against platform scope."""
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/api/search",
                headers=self._headers(),
                json={"query": query, "skip_query_expansion": False},
            )
            response.raise_for_status()
        raw_results = response.json().get("results", [])
        results: list[KnowledgeResult] = []
        for raw in raw_results:
            if len(results) >= limit:
                break
            link = raw.get("link")
            if not isinstance(link, str):
                continue
            document = await self._repository.get_by_source_uri(link, context)
            if document is None:
                continue
            results.append(
                KnowledgeResult(
                    citation_id=str(raw.get("citation_id") or f"onyx:{len(results) + 1}"),
                    document_id=document.id,
                    title=str(raw.get("title") or document.name),
                    content=self._content_security.wrap_as_evidence(
                        str(raw.get("content") or "")
                    ),
                    source_uri=document.source_uri,
                    locator={
                        "provider": "onyx",
                        "citation_id": raw.get("citation_id"),
                        "security_signals": list(
                            self._content_security.assess(
                                str(raw.get("content") or "")
                            ).signals
                        ),
                    },
                    freshness=document.updated_at,
                )
            )
        return results

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
