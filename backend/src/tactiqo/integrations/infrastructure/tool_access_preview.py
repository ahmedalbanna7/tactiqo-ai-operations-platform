"""Secret-free, bounded integration grants for the company access preview."""

from tactiqo.authorization.domain.models import EffectiveToolGrantSummary
from tactiqo.integrations.application.ports import EffectiveToolAccessRepository
from tactiqo.integrations.domain.models import ConnectionStatus
from tactiqo.shared.domain.execution import ExecutionContext

MAX_PREVIEW_CONNECTIONS = 100
MAX_PREVIEW_GRANTS = 500


class SqlEffectiveToolAccessReader:
    """Resolve effective configured grants without decrypting credentials or calling MCP."""

    def __init__(self, repository: EffectiveToolAccessRepository) -> None:
        """Configure the tenant-filtered integration repository."""
        self._repository = repository

    async def read(self, context: ExecutionContext) -> tuple[list[EffectiveToolGrantSummary], bool]:
        """Return active connection grants bounded by connection and response limits."""
        connections = await self._repository.list_active_metadata(
            context, MAX_PREVIEW_CONNECTIONS + 1
        )
        truncated = len(connections) > MAX_PREVIEW_CONNECTIONS
        result: list[EffectiveToolGrantSummary] = []
        for connection in connections[:MAX_PREVIEW_CONNECTIONS]:
            if connection.status is not ConnectionStatus.ACTIVE:
                continue
            grants = await self._repository.effective_grants(connection.id, context)
            for grant in grants:
                if len(result) == MAX_PREVIEW_GRANTS:
                    return result, True
                result.append(
                    EffectiveToolGrantSummary(
                        provider=connection.provider.value,
                        connection_name=connection.name,
                        tool_name=grant.tool_name,
                        permission=grant.permission.value,
                    )
                )
        return result, truncated
