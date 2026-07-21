"""Stable search contracts that isolate the platform from Onyx internals."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuthorizedKnowledgeQuery:
    """Represent a server-authorized knowledge query.

    Access filters are required values produced by the platform authorization
    layer. Client-supplied scope identifiers can narrow these filters but can
    never populate or widen them directly.
    """

    query_text: str
    organizational_unit_ids: tuple[str, ...]
    project_ids: tuple[str, ...]
    classification_levels: tuple[str, ...]
    source_acl_tokens: tuple[str, ...]
    maximum_results: int


@dataclass(frozen=True, slots=True)
class KnowledgeEvidence:
    """Normalize one cited passage returned by a knowledge provider."""

    source_id: str
    source_version: str
    title: str
    passage: str
    source_url: str | None
    modified_at: str | None
    synchronized_at: str
    authorization_metadata: dict[str, tuple[str, ...]]


class KnowledgeSearchPort(Protocol):
    """Provider-neutral boundary for permission-aware enterprise search."""

    async def search(
        self,
        query: AuthorizedKnowledgeQuery,
    ) -> tuple[KnowledgeEvidence, ...]:
        """Return normalized evidence after provider and platform ACL checks.

        Args:
            query: Server-authorized query with mandatory pre-retrieval filters.

        Returns:
            A bounded tuple of normalized evidence items.

        Raises:
            KnowledgeSearchUnavailable: When the configured provider is degraded.
            KnowledgeAuthorizationUncertain: When returned ACL metadata cannot be
                revalidated safely.

        """
        ...
