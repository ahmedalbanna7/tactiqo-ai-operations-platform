"""Fast deterministic orchestration routing tests."""

import pytest

from tactiqo.agents.application.execution_classifier import (
    DeterministicExecutionClassifier,
    ExecutionRoute,
)


@pytest.mark.parametrize("message", ["هاي", "Hello", "ما هي فائدة إدارة المخاطر؟"])
def test_simple_conversation_avoids_planner_and_retrieval(message: str) -> None:
    """Greetings and general questions use one direct answer call."""
    assert DeterministicExecutionClassifier().classify(message).route is ExecutionRoute.FAST


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("هات الملخص من ملف خطة المشروع", ExecutionRoute.KNOWLEDGE),
        ("ايه الملفات الموجودة في النولدج بيز؟", ExecutionRoute.KNOWLEDGE),
        ("اعرض البيانات من التقرير", ExecutionRoute.KNOWLEDGE),
        ("هات المبيعات من قاعدة البيانات", ExecutionRoute.PLANNED),
        ("ارسل ايميل للفريق", ExecutionRoute.PLANNED),
        ("ارسل تقرير المخاطر الموجود في الملف على Slack", ExecutionRoute.PLANNED_KNOWLEDGE),
        ("اي محتوي MASTER_IMPLEMENTATION_PLAN.md", ExecutionRoute.KNOWLEDGE),
        ("اي محتوي F2_SAAS_MCP_CONNECTIONS.md", ExecutionRoute.KNOWLEDGE),
        ("اي اخبار المشروع", ExecutionRoute.PLANNED_KNOWLEDGE),
    ],
)
def test_data_and_actions_take_only_the_required_route(
    message: str, expected: ExecutionRoute
) -> None:
    """Direct RAG skips planning while side effects retain it."""
    assert DeterministicExecutionClassifier().classify(message).route is expected


def test_inventory_and_structured_data_select_separate_specialists() -> None:
    """RAG inventory and operational databases never share an implicit agent."""
    classifier = DeterministicExecutionClassifier()
    inventory = classifier.classify("ما هي الملفات الموجودة في قاعدة المعرفة؟")
    structured = classifier.classify("اعرض المبيعات من SQL")

    assert inventory.reason_code == "knowledge_inventory"
    assert inventory.agent_code == "knowledge_documents"
    assert structured.reason_code == "structured_data_request"
    assert structured.agent_code == "data_analytics"


@pytest.mark.parametrize(
    "message",
    [
        "كل ملفات اللي في مصادر المعرفة",
        "اعرض المستندات المتاحة عندك",
        "ايه الموجود في النولدج بيز؟",
        "list all knowledge sources",
    ],
)
def test_inventory_intent_accepts_natural_arabic_and_english_phrasings(message: str) -> None:
    """Inventory routing must not depend on one exact user phrase."""
    decision = DeterministicExecutionClassifier().classify(message)
    assert decision.route is ExecutionRoute.KNOWLEDGE
    assert decision.reason_code == "knowledge_inventory"


def test_project_status_is_planned_by_the_pmo_agent() -> None:
    """Operational project status must not be answered as unsupported general chat."""
    decision = DeterministicExecutionClassifier().classify(
        "اعرض حالة المشروع الحالية وأهم نقاط المتابعة"
    )
    assert decision.route is ExecutionRoute.PLANNED_KNOWLEDGE
    assert decision.reason_code == "project_operations_request"
    assert decision.agent_code == "pmo"


@pytest.mark.parametrize(
    ("message", "artifact_type", "output_format", "agent_code"),
    [
        ("اعمل ليا تقرير عن الخطوات يكون pptx", "presentation", "pptx", "presentation_execution"),
        ("أنشئ ملف وورد عن المشروع", "document", "docx", "document_execution"),
        ("Generate an Excel spreadsheet for costs", "spreadsheet", "xlsx", "spreadsheet_execution"),
        ("اعمل تقرير Markdown عن الحالة", "report", "markdown", "report_execution"),
    ],
)
def test_file_creation_routes_to_output_agent(
    message: str, artifact_type: str, output_format: str, agent_code: str
) -> None:
    """Creation intent takes precedence over incidental report/knowledge markers."""
    decision = DeterministicExecutionClassifier().classify(message)
    assert decision.reason_code == "artifact_creation_request"
    assert decision.artifact_type == artifact_type
    assert decision.output_format == output_format
    assert decision.agent_code == agent_code
    assert decision.route in {ExecutionRoute.PLANNED, ExecutionRoute.PLANNED_KNOWLEDGE}


def test_artifact_mention_without_creation_is_not_executed() -> None:
    """Discussing a PPTX must not generate a file or consume quota."""
    decision = DeterministicExecutionClassifier().classify("ما معنى PPTX؟")
    assert decision.artifact_type is None
