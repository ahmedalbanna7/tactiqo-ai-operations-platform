"""Provider routing, policy, circuit and embedding-space tests."""

import builtins
from collections.abc import Sequence
from dataclasses import replace

import pytest

from tactiqo.agents.domain.models import ModelTurn
from tactiqo.ai.application.bank import AIBank, ProviderUnavailableError
from tactiqo.ai.domain.models import (
    EmbeddingResult,
    ProviderHealth,
    ProviderKind,
    ProviderProfile,
    ProviderStatus,
    embedding_space_id,
)
from tactiqo.shared.domain.execution import ExecutionContext


class MemoryProfiles:
    """Store test profiles and sanitized accounting."""

    def __init__(self, profiles: list[ProviderProfile]) -> None:
        """Initialize profile and accounting captures."""
        self.items = profiles
        self.accounting: list[str | None] = []

    async def active(self, _organization_id: str, kind: ProviderKind) -> ProviderProfile | None:
        """Return one enabled profile of the requested kind."""
        return next((item for item in self.items if item.kind is kind), None)

    async def list(self, _organization_id: str) -> list[ProviderProfile]:
        """Return test profiles."""
        return self.items

    async def enabled(
        self, _organization_id: str, kind: ProviderKind
    ) -> builtins.list[ProviderProfile]:
        """Return every enabled profile of the requested kind."""
        return [
            item
            for item in self.items
            if item.kind is kind and item.status is ProviderStatus.ENABLED
        ]

    async def upsert(self, _organization_id: str, profile: ProviderProfile, _actor_id: str) -> None:
        """Capture activation."""
        self.items = [item for item in self.items if item.name != profile.name] + [profile]

    async def disable(self, _organization_id: str, name: str, _actor_id: str) -> bool:
        """Remove one enabled profile from candidate routing."""
        if not any(item.name == name for item in self.items):
            return False
        self.items = [
            replace(item, status=ProviderStatus.DISABLED) if item.name == name else item
            for item in self.items
        ]
        return True

    async def account(
        self, _organization_id: str, _profile: str, _latency: int, _units: int, error: str | None
    ) -> None:
        """Capture only a safe error code."""
        self.accounting.append(error)


class TestAdapter:
    """Conforming adapter with controllable failure."""

    __test__ = False

    def __init__(self, *, fails: bool = False) -> None:
        """Configure success or outage behavior."""
        self.fails = fails
        self.calls = 0

    async def plan(self, *_args: object) -> ModelTurn:
        """Return multilingual text or simulate outage."""
        if self.fails:
            raise OSError
        return ModelTurn(text="يعمل محليًا — local works")

    async def answer(self, *_args: object) -> str:
        """Return a deterministic answer."""
        self.calls += 1
        if self.fails:
            raise OSError
        return "ok"

    async def embed(self, texts: Sequence[str], profile: ProviderProfile) -> EmbeddingResult:
        """Return consistent vectors in one declared space."""
        vectors = tuple((1.0, 0.0) for _ in texts)
        return EmbeddingResult(
            vectors,
            embedding_space_id("lm_studio", profile.model, "1", 2, "l2"),
            profile.model,
            2,
        )

    async def health(self, profile: ProviderProfile) -> ProviderHealth:
        """Advertise the configured model."""
        return ProviderHealth(healthy=True, latency_ms=1, models=(profile.model,))

    async def prepare(self, profile: ProviderProfile) -> ProviderHealth:
        """Represent an immediately ready provider in routing tests."""
        return ProviderHealth(healthy=True, latency_ms=1, models=(profile.model,))


def _profile(
    kind: ProviderKind, *, classifications: tuple[str, ...] = ("internal",)
) -> ProviderProfile:
    return ProviderProfile(
        f"default-{kind.value}",
        "lm_studio",
        kind,
        "local-model",
        "http://host.docker.internal:1234/v1",
        ProviderStatus.ENABLED,
        maximum_retries=0,
        allowed_classifications=classifications,
    )


def _context(classification: str = "internal") -> ExecutionContext:
    return ExecutionContext(
        "00000000-0000-4000-8000-000000000001",
        "org-a",
        "correlation",
        classification,
        "v1",
        role_codes=("owner",),
    )


@pytest.mark.anyio
async def test_switching_adapter_requires_no_agent_change() -> None:
    """The agent-facing model port routes solely from an active profile."""
    repository = MemoryProfiles([_profile(ProviderKind.LLM)])
    adapter = TestAdapter()
    bank = AIBank(repository, {"lm_studio": adapter}, {"lm_studio": adapter})
    assert (await bank.plan("مرحبا", (), (), _context())).text.startswith("يعمل")
    assert (
        'tactiqo_ai_provider_calls_total{provider="lm_studio",operation="llm_plan",'
        'outcome="success"} 1'
    ) in bank.render_metrics()


@pytest.mark.anyio
async def test_classification_negative_and_circuit_breaker() -> None:
    """Policy mismatch and repeated outages fail closed with no fallback."""
    repository = MemoryProfiles([_profile(ProviderKind.LLM)])
    adapter = TestAdapter(fails=True)
    bank = AIBank(
        repository,
        {"lm_studio": adapter},
        {"lm_studio": adapter},
        circuit_threshold=1,
    )
    with pytest.raises(ProviderUnavailableError, match="no_policy_compatible_profile"):
        await bank.plan("secret", (), (), _context("restricted"))
    with pytest.raises(ProviderUnavailableError):
        await bank.plan("hello", (), (), _context())
    with pytest.raises(ProviderUnavailableError, match="provider_circuit_open"):
        await bank.plan("hello", (), (), _context())
    assert repository.accounting == ["OSError"]
    assert (
        'tactiqo_ai_provider_calls_total{provider="lm_studio",operation="llm_plan",'
        'outcome="failure"} 1'
    ) in bank.render_metrics()


@pytest.mark.anyio
async def test_embedding_spaces_cannot_collide_across_models() -> None:
    """Model changes create different embedding-space identifiers."""
    first = embedding_space_id("lm_studio", "a", "1", 768, "l2")
    second = embedding_space_id("lm_studio", "b", "1", 768, "l2")
    assert first != second


@pytest.mark.anyio
async def test_capability_routing_falls_back_to_second_cloud_provider() -> None:
    """A failed preferred provider falls back once to another compatible profile."""
    openai = ProviderProfile(
        "openai-visual",
        "openai",
        ProviderKind.LLM,
        "openai-model",
        "https://api.openai.com/v1",
        ProviderStatus.ENABLED,
        maximum_retries=0,
        allowed_classifications=("internal",),
        capabilities=("presentation_composition",),
        routing_priority=10,
    )
    claude = ProviderProfile(
        "claude-visual-fallback",
        "claude",
        ProviderKind.LLM,
        "claude-model",
        "https://api.anthropic.com/v1",
        ProviderStatus.ENABLED,
        maximum_retries=0,
        allowed_classifications=("internal",),
        capabilities=("presentation_composition",),
        routing_priority=20,
    )
    preferred = TestAdapter(fails=True)
    fallback = TestAdapter()
    bank = AIBank(
        MemoryProfiles([openai, claude]),
        {"openai": preferred, "claude": fallback},
        {},
    )

    result = await bank.answer_for(
        "presentation_composition", "create deck", (), (), _context()
    )

    assert result == "ok"
    assert preferred.calls == 1
    assert fallback.calls == 1


@pytest.mark.anyio
async def test_cloud_activation_and_disable_switches_back_to_local() -> None:
    """Local serves until cloud is enabled, then returns immediately when disabled."""
    local = _profile(ProviderKind.LLM)
    cloud = ProviderProfile(
        "cloud", "openai", ProviderKind.LLM, "cloud-model",
        "https://api.openai.com/v1", ProviderStatus.ENABLED,
        maximum_retries=0, allowed_classifications=("internal",), routing_priority=10,
    )
    repository = MemoryProfiles([local, cloud])
    local_adapter = TestAdapter()
    cloud_adapter = TestAdapter()
    bank = AIBank(repository, {"lm_studio": local_adapter, "openai": cloud_adapter}, {})

    assert await bank.answer("hello", (), (), _context()) == "ok"
    assert cloud_adapter.calls == 1
    assert local_adapter.calls == 0
    assert await bank.disable(_context(), "cloud")
    assert await bank.answer("hello", (), (), _context()) == "ok"
    assert local_adapter.calls == 1
