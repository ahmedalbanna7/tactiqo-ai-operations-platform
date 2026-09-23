"""Policy-aware LLM and embedding routing with bounded failure handling."""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from time import monotonic
from typing import TypeVar
from urllib.parse import urlparse

from tactiqo.agents.domain.models import ModelTurn
from tactiqo.ai.application.ports import EmbeddingAdapter, LLMAdapter, ProviderProfileRepository
from tactiqo.ai.application.telemetry import ProviderCallMetrics
from tactiqo.ai.domain.models import (
    AICapability,
    EmbeddingResult,
    ProviderHealth,
    ProviderKind,
    ProviderProfile,
)
from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.knowledge.domain.models import KnowledgeResult
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ToolDefinition, ToolResult


class ProviderUnavailableError(RuntimeError):
    """A configured provider cannot safely serve the request."""


T = TypeVar("T")
MAX_EMBEDDING_BATCH = 64
MAX_EMBEDDING_TEXT = 16_000
LM_STUDIO_PORT = 1234


class AIBank:
    """Route both AI capability families without exposing vendor adapters."""

    def __init__(
        self,
        repository: ProviderProfileRepository,
        llm_adapters: dict[str, LLMAdapter],
        embedding_adapters: dict[str, EmbeddingAdapter],
        *,
        circuit_threshold: int = 3,
        circuit_cooldown_seconds: float = 30,
    ) -> None:
        """Configure registries and bounded circuit behavior."""
        self._repository = repository
        self._llms = llm_adapters
        self._embeddings = embedding_adapters
        self._failures: dict[str, int] = defaultdict(int)
        self._opened_until: dict[str, float] = defaultdict(float)
        self._circuit_threshold = circuit_threshold
        self._cooldown = circuit_cooldown_seconds
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._provider_metrics = ProviderCallMetrics()

    def render_metrics(self) -> str:
        """Expose bounded, process-local provider metrics to the protected scrape endpoint."""
        return self._provider_metrics.render_prometheus()

    async def plan(
        self,
        message: str,
        evidence: Sequence[KnowledgeResult],
        tools: Sequence[ToolDefinition],
        context: ExecutionContext,
    ) -> ModelTurn:
        """Route planning through the tenant's active LLM profile."""
        return await self._execute_llm_candidates(
            context,
            AICapability.REASONING,
            lambda adapter, profile: adapter.plan(message, evidence, tools, context, profile),
            len(message),
            "llm_plan",
        )

    async def answer(
        self,
        message: str,
        evidence: Sequence[KnowledgeResult],
        tool_results: Sequence[ToolResult],
        context: ExecutionContext,
    ) -> str:
        """Route final synthesis through the active LLM profile."""
        return await self.answer_for(
            AICapability.GENERAL.value, message, evidence, tool_results, context
        )

    async def answer_for(
        self,
        capability: str,
        message: str,
        evidence: Sequence[KnowledgeResult],
        tool_results: Sequence[ToolResult],
        context: ExecutionContext,
    ) -> str:
        """Use the best healthy policy-compatible LLM, then a bounded fallback."""
        return await self._execute_llm_candidates(
            context,
            AICapability(capability),
            lambda adapter, profile: adapter.answer(
                message, evidence, tool_results, context, profile
            ),
            len(message),
            "llm_answer",
        )

    async def embed(self, texts: Sequence[str], context: ExecutionContext) -> EmbeddingResult:
        """Route a bounded batch through the active embedding profile."""
        if (
            not texts
            or len(texts) > MAX_EMBEDDING_BATCH
            or any(len(text) > MAX_EMBEDDING_TEXT for text in texts)
        ):
            message_text = "embedding_batch_out_of_bounds"
            raise ValueError(message_text)
        profile = await self._profile(context, ProviderKind.EMBEDDING)
        adapter = self._embeddings.get(profile.provider)
        if adapter is None:
            message_text = "provider_adapter_missing"
            raise ProviderUnavailableError(message_text)
        return await self._execute(
            context,
            profile,
            lambda: adapter.embed(texts, profile),
            sum(len(text) for text in texts),
            "embedding",
        )

    async def test(self, profile: ProviderProfile) -> ProviderHealth:
        """Test a candidate profile without activating it."""
        if not self._safe_endpoint(profile):
            return ProviderHealth(healthy=False, latency_ms=0, error_code="endpoint_not_allowed")
        adapter = (
            self._llms.get(profile.provider)
            if profile.kind is ProviderKind.LLM
            else self._embeddings.get(profile.provider)
        )
        if adapter is None:
            return ProviderHealth(
                healthy=False, latency_ms=0, error_code="provider_adapter_missing"
            )
        return await adapter.health(profile)

    async def profiles(self, context: ExecutionContext) -> list[ProviderProfile]:
        """List non-secret profiles for an administrator."""
        self._require_admin(context)
        return await self._repository.list(context.organization_id)

    def require_admin(self, context: ExecutionContext) -> None:
        """Authorize an Owner-only playground request before provider access."""
        self._require_admin(context)

    async def disable(self, context: ExecutionContext, name: str) -> bool:
        """Stop routing new calls to one profile immediately."""
        self._require_admin(context)
        return await self._repository.disable(context.organization_id, name, context.actor_id)

    async def configure(
        self, context: ExecutionContext, profile: ProviderProfile
    ) -> ProviderHealth:
        """Validate and atomically activate a candidate profile."""
        self._require_admin(context)
        if profile.provider != "lm_studio" and not profile.secret_reference:
            current = next(
                (
                    item
                    for item in await self._repository.list(context.organization_id)
                    if item.name == profile.name and item.provider == profile.provider
                ),
                None,
            )
            if current is not None:
                profile = replace(profile, secret_reference=current.secret_reference)
        health = await self.test(profile)
        if not health.healthy or profile.model not in health.models:
            return health
        adapter = (
            self._llms[profile.provider]
            if profile.kind is ProviderKind.LLM
            else self._embeddings[profile.provider]
        )
        health = await adapter.prepare(profile)
        if not health.healthy:
            return health
        await self._repository.upsert(context.organization_id, profile, context.actor_id)
        return health

    async def _profile(self, context: ExecutionContext, kind: ProviderKind) -> ProviderProfile:
        profile = await self._repository.active(context.organization_id, kind)
        if (
            profile is None
            or context.classification_clearance not in profile.allowed_classifications
        ):
            message_text = "no_policy_compatible_profile"
            raise ProviderUnavailableError(message_text)
        if self._opened_until[profile.name] > monotonic():
            message_text = "provider_circuit_open"
            raise ProviderUnavailableError(message_text)
        return profile

    async def _execute_llm_candidates(
        self,
        context: ExecutionContext,
        capability: AICapability,
        operation: Callable[[LLMAdapter, ProviderProfile], Awaitable[T]],
        units: int,
        telemetry_operation: str,
    ) -> T:
        profiles = await self._repository.enabled(context.organization_id, ProviderKind.LLM)
        compatible = [
            profile
            for profile in profiles
            if context.classification_clearance in profile.allowed_classifications
            and (
                capability.value in profile.capabilities
                or AICapability.GENERAL.value in profile.capabilities
            )
        ]
        provider_preference = {
            AICapability.DOCUMENT_ANALYSIS: {"claude": 0, "openai": 1, "lm_studio": 2},
            AICapability.PRESENTATION_COMPOSITION: {
                "openai": 0,
                "claude": 1,
                "lm_studio": 2,
            },
        }.get(capability, {"lm_studio": 0, "openai": 1, "claude": 2})
        compatible.sort(
            key=lambda item: (item.routing_priority, provider_preference.get(item.provider, 50))
        )
        errors: list[str] = []
        for profile in compatible:
            adapter = self._llms.get(profile.provider)
            if adapter is None:
                continue
            if self._opened_until[profile.name] > monotonic():
                errors.append("provider_circuit_open")
                continue
            try:
                return await self._execute(
                    context,
                    profile,
                    lambda adapter=adapter, profile=profile: operation(adapter, profile),
                    units,
                    telemetry_operation,
                )
            except ProviderUnavailableError as error:
                errors.append(str(error))
        message_text = errors[-1] if errors else "no_policy_compatible_profile"
        raise ProviderUnavailableError(message_text)

    async def _execute(
        self,
        context: ExecutionContext,
        profile: ProviderProfile,
        operation: Callable[[], Awaitable[T]],
        units: int,
        telemetry_operation: str,
    ) -> T:
        started = monotonic()
        error: str | None = None
        outcome = "failure"
        try:
            semaphore = self._semaphores.setdefault(
                profile.name, asyncio.Semaphore(profile.maximum_concurrency)
            )
            async with semaphore:
                for attempt in range(profile.maximum_retries + 1):
                    try:
                        async with asyncio.timeout(profile.timeout_seconds):
                            result = await operation()
                    except (TimeoutError, OSError):
                        if attempt >= profile.maximum_retries:
                            raise
                        await asyncio.sleep(min(0.1 * (2**attempt), 1))
            self._failures[profile.name] = 0
            outcome = "success"
        except Exception as exc:
            error = type(exc).__name__
            self._failures[profile.name] += 1
            if self._failures[profile.name] >= self._circuit_threshold:
                self._opened_until[profile.name] = monotonic() + self._cooldown
            raise ProviderUnavailableError(error) from exc
        else:
            return result
        finally:
            self._provider_metrics.observe(
                profile.provider,
                telemetry_operation,
                outcome,
                (monotonic() - started) * 1000,
            )
            await self._repository.account(
                context.organization_id,
                profile.name,
                int((monotonic() - started) * 1000),
                units,
                error,
            )

    @staticmethod
    def _require_admin(context: ExecutionContext) -> None:
        if not {
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }.intersection(context.role_codes):
            raise AdministrationDeniedError

    @staticmethod
    def _safe_endpoint(profile: ProviderProfile) -> bool:
        parsed = urlparse(profile.endpoint)
        if profile.provider == "openai":
            return (
                parsed.scheme == "https"
                and parsed.hostname == "api.openai.com"
                and parsed.port is None
                and parsed.path.rstrip("/") == "/v1"
            )
        if profile.provider == "claude":
            return (
                parsed.scheme == "https"
                and parsed.hostname == "api.anthropic.com"
                and parsed.port is None
                and parsed.path.rstrip("/") == "/v1"
            )
        return (
            profile.provider == "lm_studio"
            and parsed.scheme == "http"
            and parsed.hostname in {"host.docker.internal", "127.0.0.1", "localhost"}
            and parsed.port == LM_STUDIO_PORT
            and parsed.path.rstrip("/") == "/v1"
        )
