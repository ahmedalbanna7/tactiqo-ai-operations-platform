"""Provider-neutral model-turn and guardrail values."""

from dataclasses import dataclass, field

from tactiqo.tools.domain.models import ToolCall


@dataclass(frozen=True, slots=True)
class ModelTurn:
    """One model planning result before platform policy execution."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """Deterministic input review result."""

    allowed: bool
    tool_execution_allowed: bool
    reason_code: str
