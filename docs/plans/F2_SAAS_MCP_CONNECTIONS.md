# F2 SaaS MCP connections

## Scope and assumptions

Deliver tenant-owned Jira and Slack MCP connections. Connections are created by
an authenticated user or account manager and are never process-wide settings.
F1 still uses the local identity adapter; production identity and account-manager
roles must replace it before a public deployment.

## Repository assessment

The F1 gateway was composed once at process startup and read remote credentials
from environment variables. `ToolGateway.list_tools` had no execution context,
so it could not enforce tenant isolation during discovery.

## Architecture and affected modules

- Add an integrations domain, application service, SQL repository and credential
  encryption port.
- Resolve enabled connections for every server-derived `ExecutionContext`.
- Pass context through both tool discovery and invocation.
- Keep vendor MCP SDK objects inside infrastructure adapters.

## Data model and migration

`integration_connections` is the PostgreSQL source of truth. Every row includes
`organization_id`, optional `owner_actor_id`, provider, endpoint, encrypted
authorization material, status and audit timestamps. Unique names are scoped to
an organization. Secrets are never returned by APIs or written to audit logs.

## API, event and job contracts

- `POST /api/v1/integrations/connections`
- `GET /api/v1/integrations/connections`
- `DELETE /api/v1/integrations/connections/{id}`
- `POST /api/v1/integrations/connections/{id}/verify`

Provider OAuth applications may exchange and rotate tokens outside this API;
their resulting authorization material is supplied through the same encrypted
connection contract. A later identity phase can add hosted OAuth start/callback
routes without changing agents or the MCP gateway.

## Security and authorization impact

Tenant predicates are applied in SQL before a connection is returned. Personal
connections additionally require an actor match. Credentials use Fernet
authenticated encryption with a deployment-owned key. URLs require HTTPS except
for explicitly local development endpoints. Mutating tools retain durable human
approval and append-only audit behavior.

## Capacity, backpressure and failure handling

Discovery remains bounded to 20 MCP pages. Each connection uses bounded HTTP
timeouts and result sizes. One unavailable provider fails its verification and
is not silently treated as connected. Revocation is a soft disable followed by
credential removal from the active resolver.

## Human approval requirements

Creating or revoking a connection is an explicit user/account-manager action.
Every MCP mutation still pauses the LangGraph run for approval. Provider-side
consent remains visible to the user during OAuth.

## Tests, observability and documentation

Tests cover encryption, tenant isolation, scoped discovery and fail-closed
validation. Logs expose connection IDs/provider/status only, never secrets.
Rollback disables SaaS connection resolution and downgrades the migration.

## Open deployment decisions

Production identity provider, account-manager role mapping, KMS/HSM key custody,
and public OAuth callback domains remain deployment decisions. They do not alter
the domain or agent contracts introduced here.
