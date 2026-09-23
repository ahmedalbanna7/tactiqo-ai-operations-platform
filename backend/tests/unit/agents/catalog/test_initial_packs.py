"""Completeness and stability checks for the built-in agent catalog."""

from tactiqo.agents.catalog.domain.models import INITIAL_AGENT_PACKS, AgentCategory


def test_initial_agent_codes_are_unique() -> None:
    """Stable codes must never shadow another installed agent."""
    codes = [item.code for item in INITIAL_AGENT_PACKS]
    assert len(codes) == len(set(codes))


def test_f8_execution_agents_are_explicitly_registered() -> None:
    """Every F8 output family has an independently assignable policy resource."""
    expected = {
        "email_execution",
        "report_execution",
        "document_execution",
        "presentation_execution",
        "spreadsheet_execution",
        "power_bi_execution",
        "image_execution",
        "video_execution",
        "meeting_calendar_execution",
        "data_operations_execution",
        "social_campaign_execution",
        "automation_integrations",
    }
    by_code = {item.code: item for item in INITIAL_AGENT_PACKS}
    assert expected <= by_code.keys()
    assert all(
        by_code[code].category
        in {
            AgentCategory.EXECUTION_CONTENT,
            AgentCategory.DATA_BI,
            AgentCategory.AUTOMATION_INTEGRATIONS,
        }
        for code in expected
    )
