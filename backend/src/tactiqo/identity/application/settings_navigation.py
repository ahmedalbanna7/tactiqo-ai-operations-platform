"""Server-derived Company Settings navigation without client-side authority claims."""

from dataclasses import dataclass

from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.shared.domain.execution import ExecutionContext


@dataclass(frozen=True, slots=True)
class SettingsSection:
    """One non-secret settings entry permitted for the caller."""

    code: str
    label: str


class CompanySettingsNavigation:
    """Present only settings backed by an existing guarded API surface."""

    @staticmethod
    def sections(context: ExecutionContext) -> tuple[SettingsSection, ...]:
        """Use server-derived roles; API handlers still reauthorize every operation."""
        roles = set(context.role_codes)
        if roles.intersection({
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }):
            return (
                SettingsSection("overview", "نظرة عامة"),
                SettingsSection("ai", "الذكاء والموديلات"),
                SettingsSection("artifacts", "سياسة المخرجات"),
                SettingsSection("people", "الموظفون"),
                SettingsSection("structure", "هيكل الشركة"),
                SettingsSection("agents", "صلاحيات الوكلاء"),
                SettingsSection("integrations", "التكاملات"),
                SettingsSection("knowledge", "معرفة الشركة"),
                SettingsSection("jobs", "المهام"),
            )
        if OrganizationRole.INTEGRATION_MANAGER.value in roles:
            return (SettingsSection("integrations", "التكاملات"),)
        return ()
