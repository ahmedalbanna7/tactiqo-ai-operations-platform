"""F9 settings navigation is derived from server roles, never client claims."""

from unittest.mock import AsyncMock

import pytest

from tactiqo.identity.application.administration import (
    AdministrationDeniedError,
    OrganizationAdministrationService,
)
from tactiqo.identity.application.settings_navigation import CompanySettingsNavigation
from tactiqo.shared.domain.execution import ExecutionContext


def _context(*roles: str) -> ExecutionContext:
    return ExecutionContext("actor", "tenant", "corr", "internal", "v1", role_codes=roles)


def test_owner_sees_guarded_settings_destinations() -> None:
    """Owner receives only implemented destination codes."""
    codes = {item.code for item in CompanySettingsNavigation.sections(_context("owner"))}
    assert codes == {
        "overview", "ai", "artifacts", "people", "structure", "agents", "integrations",
        "knowledge", "jobs",
    }


def test_employee_cannot_discover_company_settings() -> None:
    """An ordinary employee has no administrative navigation metadata."""
    assert CompanySettingsNavigation.sections(_context("employee")) == ()


def test_integration_manager_only_sees_integration_section() -> None:
    """Integration management does not imply AI or company-knowledge authority."""
    sections = CompanySettingsNavigation.sections(_context("integration_manager"))
    assert tuple(item.code for item in sections) == ("integrations",)


@pytest.mark.anyio
async def test_company_structure_api_use_case_denies_employee() -> None:
    """Direct API access cannot bypass the hidden employee navigation."""
    repository = AsyncMock()
    service = OrganizationAdministrationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.list_units(_context("employee"))
    repository.list_units.assert_not_awaited()

    repository.list_units.return_value = []
    assert await service.list_units(_context("owner")) == []
    repository.list_units.assert_awaited_once_with("tenant")


@pytest.mark.anyio
async def test_people_directory_denies_employee() -> None:
    """Direct people API use case cannot expose names to ordinary employees."""
    repository = AsyncMock()
    service = OrganizationAdministrationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.list_people(_context("employee"))
    repository.list_people.assert_not_awaited()
