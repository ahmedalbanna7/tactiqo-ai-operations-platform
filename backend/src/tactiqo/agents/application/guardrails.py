"""Deterministic input guardrails that cannot be overridden by prompts."""

import re

from tactiqo.agents.domain.models import GuardrailResult

_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"تجاهل\s+(كل\s+)?التعليمات", re.IGNORECASE),
    re.compile(r"اكشف\s+تعليمات\s+النظام", re.IGNORECASE),
)


class InputGuardrails:
    """Bound input size and disable tools for direct instruction attacks."""

    def __init__(self, maximum_characters: int = 12_000) -> None:
        """Configure the maximum accepted input size."""
        self._maximum_characters = maximum_characters

    def evaluate(self, message: str) -> GuardrailResult:
        """Return a stable safety decision before retrieval or tools."""
        normalized = message.strip()
        if not normalized:
            return GuardrailResult(
                allowed=False,
                tool_execution_allowed=False,
                reason_code="empty_message",
            )
        if len(normalized) > self._maximum_characters:
            return GuardrailResult(
                allowed=False,
                tool_execution_allowed=False,
                reason_code="message_too_large",
            )
        if any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS):
            return GuardrailResult(
                allowed=True,
                tool_execution_allowed=False,
                reason_code="tool_use_restricted_prompt_injection",
            )
        return GuardrailResult(
            allowed=True,
            tool_execution_allowed=True,
            reason_code="input_allowed",
        )
