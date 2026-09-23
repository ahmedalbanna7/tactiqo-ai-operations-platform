# ruff: noqa: RUF001, SLF001
"""Conversation context-window behavior tests."""

from datetime import UTC, datetime
from uuid import uuid4

from tactiqo.agents.application.orchestrator import AgentOrchestrator
from tactiqo.chat.domain.models import Message, MessageRole


def _message(role: MessageRole, content: str) -> Message:
    return Message(uuid4(), uuid4(), role, content, datetime.now(UTC))


def test_memory_window_keeps_summary_pending_history_and_recent_five_turns() -> None:
    """The current prompt context has a bounded recent window and no data loss."""
    pending = [_message(MessageRole.USER, "قرار قديم غير ملخص")]
    recent = [
        _message(MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT, f"m{index}")
        for index in range(10)
    ]

    rendered = AgentOrchestrator._render_memory("الملخص السابق", pending, recent)

    assert "الملخص السابق" in rendered
    assert "قرار قديم غير ملخص" in rendered
    assert "m0" in rendered
    assert "m9" in rendered


def test_current_message_is_appended_after_memory_as_an_explicit_section() -> None:
    """Historical text cannot be confused with the user's current instruction."""
    rendered = AgentOrchestrator._model_message(
        {"message": "السؤال الحالي", "conversation_context": "ملخص سابق"}
    )

    assert "reference only" in rendered
    assert rendered.endswith("Current user message:\nالسؤال الحالي")
