"""Provider-neutral AI configuration and result values."""

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum


class ProviderKind(StrEnum):
    """AI capability families routed independently."""

    LLM = "llm"
    EMBEDDING = "embedding"


class AICapability(StrEnum):
    """Vendor-neutral work families used by routing policy."""

    GENERAL = "general"
    FAST_CHAT = "fast_chat"
    REASONING = "reasoning"
    DOCUMENT_ANALYSIS = "document_analysis"
    PRESENTATION_COMPOSITION = "presentation_composition"
    STRUCTURED_EXTRACTION = "structured_extraction"


class ProviderStatus(StrEnum):
    """Administrative provider lifecycle."""

    REGISTERED = "registered"
    VALIDATED = "validated"
    ENABLED = "enabled"
    DRAINING = "draining"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Tenant-owned routing profile without secret material."""

    name: str
    provider: str
    kind: ProviderKind
    model: str
    endpoint: str
    status: ProviderStatus
    version: int = 1
    secret_reference: str | None = None
    timeout_seconds: float = 90
    maximum_retries: int = 1
    maximum_concurrency: int = 1
    daily_unit_limit: int = 100_000
    allowed_classifications: tuple[str, ...] = ("public", "internal", "confidential", "restricted")
    capabilities: tuple[str, ...] = (AICapability.GENERAL.value,)
    routing_priority: int = 100


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Vectors tied to one immutable embedding space."""

    vectors: tuple[tuple[float, ...], ...]
    embedding_space_id: str
    model: str
    dimensions: int


def embedding_space_id(
    provider: str, model: str, version: str, dimensions: int, normalization: str
) -> str:
    """Create a stable identity that prevents cross-space comparison."""
    raw = f"{provider}|{model}|{version}|{dimensions}|{normalization}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Sanitized connection status."""

    healthy: bool
    latency_ms: int
    models: tuple[str, ...] = field(default_factory=tuple)
    error_code: str | None = None
