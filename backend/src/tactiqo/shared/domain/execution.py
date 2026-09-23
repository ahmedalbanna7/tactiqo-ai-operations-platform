"""Stable execution context propagated through agentic workflows."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Server-derived actor and data scope for one operation.

    F1 composes this value through a local-only provider. Later identity and
    authorization modules replace that provider without changing consumers.
    """

    actor_id: str
    organization_id: str
    correlation_id: str
    classification_clearance: str
    policy_version: str
    organizational_unit_ids: tuple[str, ...] = field(default_factory=tuple)
    department_ids: tuple[str, ...] = field(default_factory=tuple)
    team_ids: tuple[str, ...] = field(default_factory=tuple)
    project_ids: tuple[str, ...] = field(default_factory=tuple)
    role_codes: tuple[str, ...] = field(default_factory=tuple)
    data_region: str = "global"
    session_id: str | None = None
    session_assurance: str = "standard"

    def audit_metadata(self) -> dict[str, str | list[str]]:
        """Return non-secret scope metadata suitable for durable audit events."""
        return {
            "actor_id": self.actor_id,
            "organization_id": self.organization_id,
            "correlation_id": self.correlation_id,
            "classification_clearance": self.classification_clearance,
            "policy_version": self.policy_version,
            "organizational_unit_ids": list(self.organizational_unit_ids),
            "department_ids": list(self.department_ids),
            "team_ids": list(self.team_ids),
            "project_ids": list(self.project_ids),
            "role_codes": list(self.role_codes),
            "data_region": self.data_region,
            "session_id": self.session_id or "",
            "session_assurance": self.session_assurance,
        }
