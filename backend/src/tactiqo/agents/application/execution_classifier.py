"""Deterministic execution routing before any model or retrieval call."""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar

from tactiqo.agents.domain.planning import WorkClass, WorkEstimate


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Configurable deterministic boundaries for foreground work."""

    maximum_input_characters: int = 8_000
    maximum_foreground_files: int = 3
    maximum_foreground_media: int = 0
    maximum_foreground_records: int = 1_000
    maximum_foreground_steps: int = 4
    maximum_foreground_tools: int = 2


class ExecutionRoute(StrEnum):
    """Small, auditable graph routes with no model dependency."""

    FAST = "fast"
    KNOWLEDGE = "knowledge"
    PLANNED = "planned"
    PLANNED_KNOWLEDGE = "planned_knowledge"


OPERATIONAL_AGENT_CODES = frozenset({
    "chat_assistant",
    "planner",
    "pmo",
    "knowledge_documents",
    "data_analytics",
    "report_execution",
    "document_execution",
    "presentation_execution",
    "spreadsheet_execution",
})


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    """A content-free reason suitable for durable audit events."""

    route: ExecutionRoute
    reason_code: str
    work_class: WorkClass = WorkClass.FAST
    estimate: WorkEstimate = field(default_factory=lambda: WorkEstimate(input_characters=0))
    artifact_type: str | None = None
    output_format: str | None = None

    @property
    def agent_code(self) -> str:
        """Map each route to the least-privileged specialist agent."""
        artifact_agents = {
            "report": "report_execution",
            "document": "document_execution",
            "presentation": "presentation_execution",
            "spreadsheet": "spreadsheet_execution",
        }
        if self.artifact_type in artifact_agents:
            return artifact_agents[self.artifact_type]
        if self.reason_code == "structured_data_request":
            return "data_analytics"
        if self.reason_code == "project_operations_request":
            return "pmo"
        if self.route in {ExecutionRoute.KNOWLEDGE, ExecutionRoute.PLANNED_KNOWLEDGE}:
            return "knowledge_documents"
        if self.route is ExecutionRoute.PLANNED:
            return "planner"
        return "chat_assistant"


class DeterministicExecutionClassifier:
    """Keep common chat and direct retrieval off the expensive Planner path."""

    _greetings: ClassVar[set[str]] = {
        "hi",
        "hello",
        "hey",
        "مرحبا",
        "مرحباً",
        "هاي",
        "السلام عليكم",
        "صباح الخير",
        "مساء الخير",
        "شكرا",
        "شكراً",
    }
    _knowledge_markers: ClassVar[tuple[str, ...]] = (
        "file",
        "document",
        "report",
        "knowledge",
        "source",
        "attachment",
        "ملف",
        "مستند",
        "تقرير",
        "المعرفة",
        "مصدر",
        "مرفق",
        "الداتا",
        "البيانات",
    )
    _inventory_markers: ClassVar[tuple[str, ...]] = (
        "list files",
        "what files",
        "which files",
        "available documents",
        "قائمة الملفات",
        "الملفات الموجودة",
        "اي الملفات",
        "إيه الملفات",
        "ما الملفات",
        "ما هي الملفات",
        "ايه الملفات",
        "المستندات الموجودة",
    )
    _inventory_entities: ClassVar[tuple[str, ...]] = (
        "files",
        "documents",
        "sources",
        "ملفات",
        "الملفات",
        "مستندات",
        "المستندات",
        "مصادر المعرفة",
        "قاعدة المعرفة",
        "النولدج بيز",
    )
    _inventory_intents: ClassVar[tuple[str, ...]] = (
        "list",
        "all",
        "what",
        "which",
        "available",
        "كل",
        "قائمة",
        "اعرض",
        "اظهر",
        "أظهر",
        "اي",
        "إيه",
        "ايه",
        "ما ",
        "الموجود",
        "المتاحة",
    )
    _structured_data_markers: ClassVar[tuple[str, ...]] = (
        "sql",
        "nosql",
        "database",
        "data warehouse",
        "قاعدة البيانات",
        "قواعد البيانات",
        "داتا بيز",
    )
    _project_operations_markers: ClassVar[tuple[str, ...]] = (
        "project status",
        "project tasks",
        "project follow-up",
        "حالة المشروع",
        "مهام المشروع",
        "متابعة المشروع",
        "نقاط المتابعة",
        "البنود المتأخرة",
        "اخبار المشروع",
        "أخبار المشروع",
        "وضع المشروع",
        "تقدم المشروع",
    )
    _action_markers: ClassVar[tuple[str, ...]] = (
        "send ",
        "create ",
        "update ",
        "delete ",
        "schedule ",
        "jira",
        "slack",
        "email",
        "ارسل",
        "إرسال",
        "انشئ",
        "أنشئ",
        "حدث ",
        "عدّل",
        "احذف",
        "جدول",
        "جيرا",
        "سلاك",
        "ايميل",
        "بريد",
    )
    _complexity_markers: ClassVar[tuple[str, ...]] = (
        "then",
        "after that",
        "workflow",
        "automation",
        "خطوات",
        "ثم ",
        "وبعدين",
        "بعد كده",
        "أتمتة",
        "اوتوميشن",
    )
    _background_markers: ClassVar[tuple[str, ...]] = (
        "large file",
        "video",
        "many files",
        "bulk",
        "ملف كبير",
        "فيديو",
        "ملفات كثيرة",
        "دفعة كبيرة",
    )
    _artifact_formats: ClassVar[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
        (
            "presentation",
            "pptx",
            ("pptx", "powerpoint", "power point", "بوربوينت", "عرض تقديمي", "عرض باوربوينت"),
        ),
        ("document", "docx", ("docx", "word document", "word file", "ملف وورد", "مستند وورد")),
        ("spreadsheet", "xlsx", ("xlsx", "excel", "spreadsheet", "اكسل", "إكسل", "جدول بيانات")),
        (
            "report",
            "markdown",
            ("markdown report", "md report", "تقرير markdown", "تقرير ماركداون"),
        ),
    )
    _artifact_creation_markers: ClassVar[tuple[str, ...]] = (
        "create", "generate", "build", "make", "export",
        "اعمل", "أنشئ", "انشئ", "جهز", "صدّر", "صدر",
    )

    def __init__(self, limits: ExecutionLimits | None = None) -> None:
        """Configure hard foreground limits without provider dependencies."""
        self._limits = limits or ExecutionLimits()

    def classify(self, message: str) -> ExecutionDecision:  # noqa: PLR0911
        """Choose a conservative route using bounded lexical signals only."""
        normalized = " ".join(message.casefold().strip().split())
        estimate = self._estimate(normalized)
        has_background_marker = any(marker in normalized for marker in self._background_markers)
        background = has_background_marker or self.should_escalate(estimate)
        work_class = WorkClass.BACKGROUND if background else WorkClass.STANDARD
        if normalized in self._greetings:
            return ExecutionDecision(
                ExecutionRoute.FAST, "simple_conversation", WorkClass.FAST, estimate
            )
        artifact = self._artifact_request(normalized)
        if artifact is not None:
            artifact_type, output_format = artifact
            needs_knowledge = any(marker in normalized for marker in self._knowledge_markers)
            route = (
                ExecutionRoute.PLANNED_KNOWLEDGE
                if needs_knowledge
                else ExecutionRoute.PLANNED
            )
            return ExecutionDecision(
                route,
                "artifact_creation_request",
                work_class,
                estimate,
                artifact_type,
                output_format,
            )
        explicit_inventory = any(marker in normalized for marker in self._inventory_markers)
        composed_inventory = any(
            entity in normalized for entity in self._inventory_entities
        ) and any(intent in normalized for intent in self._inventory_intents)
        if explicit_inventory or composed_inventory:
            return ExecutionDecision(
                ExecutionRoute.KNOWLEDGE, "knowledge_inventory", WorkClass.FAST, estimate
            )
        if any(marker in normalized for marker in self._structured_data_markers):
            return ExecutionDecision(
                ExecutionRoute.PLANNED, "structured_data_request", work_class, estimate
            )
        if any(marker in normalized for marker in self._project_operations_markers):
            return ExecutionDecision(
                ExecutionRoute.PLANNED_KNOWLEDGE,
                "project_operations_request",
                work_class,
                estimate,
            )
        named_document = re.search(r"\b[\w.-]+\.(?:md|pdf|docx|xlsx|pptx|csv|txt)\b", normalized)
        needs_knowledge = bool(named_document) or any(
            marker in normalized for marker in self._knowledge_markers
        )
        needs_action = any(marker in normalized for marker in self._action_markers)
        is_complex = any(marker in normalized for marker in self._complexity_markers)
        if needs_action and needs_knowledge:
            return ExecutionDecision(
                ExecutionRoute.PLANNED_KNOWLEDGE, "action_with_evidence", work_class, estimate
            )
        if needs_action or is_complex:
            return ExecutionDecision(
                ExecutionRoute.PLANNED, "tool_or_multistep_request", work_class, estimate
            )
        if needs_knowledge:
            return ExecutionDecision(
                ExecutionRoute.KNOWLEDGE, "direct_knowledge_request", WorkClass.FAST, estimate
            )
        return ExecutionDecision(
            ExecutionRoute.FAST, "direct_conversation", WorkClass.FAST, estimate
        )

    @classmethod
    def _artifact_request(cls, normalized: str) -> tuple[str, str] | None:
        """Recognize explicit file creation without asking a model to choose capabilities."""
        if not any(marker in normalized for marker in cls._artifact_creation_markers):
            return None
        for artifact_type, output_format, markers in cls._artifact_formats:
            if any(marker in normalized for marker in markers):
                return artifact_type, output_format
        return None

    @classmethod
    def _estimate(cls, normalized: str) -> WorkEstimate:
        action_count = sum(marker in normalized for marker in cls._action_markers)
        complexity_count = sum(marker in normalized for marker in cls._complexity_markers)
        media_count = int(
            any(marker in normalized for marker in ("video", "audio", "فيديو", "صوت"))
        )
        file_count = int(any(marker in normalized for marker in cls._knowledge_markers))
        risk_score = min(100, action_count * 25 + complexity_count * 10)
        return WorkEstimate(
            input_characters=len(normalized),
            file_count=file_count,
            media_count=media_count,
            tool_count=action_count,
            step_count=max(1, 1 + complexity_count),
            risk_score=risk_score,
            approval_count=int(action_count > 0),
        )

    def should_escalate(self, estimate: WorkEstimate) -> bool:
        """Escalate safely at a checkpoint before any new side effect is proposed."""
        return (
            estimate.input_characters > self._limits.maximum_input_characters
            or estimate.file_count > self._limits.maximum_foreground_files
            or estimate.media_count > self._limits.maximum_foreground_media
            or estimate.record_count > self._limits.maximum_foreground_records
            or estimate.step_count > self._limits.maximum_foreground_steps
            or estimate.tool_count > self._limits.maximum_foreground_tools
        )
