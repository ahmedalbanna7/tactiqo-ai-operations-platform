# F6 — SaaS MCP Connections and Scoped Tool Management

Status: core Jira/Slack SaaS connection and scoped-tool control plane implemented. Live provider
acceptance remains environment-gated by customer workspaces and OAuth consent.

## Implemented checkpoint

- Owner/Admin/Integration Manager authorization for organization connection lifecycle.
- Personal connections remain restricted to their owner.
- Explicit organization/department/team/project/agent/user tool grants.
- Read, draft, execute, and administer permissions with exact-tool or explicit wildcard matching.
- Fail-closed discovery before model context and revalidation before every call.
- Reconnect/credential rotation and explicit disabled, expired, error, and revoked states.
- Secret-free grant APIs and Arabic UI controls.
- Migration `20260914_0008`; existing connections receive no implicit grants.

## Scope and assumptions

Jira and Slack remain the first providers. Organization connections may be managed only by an
Owner, Organization Admin, or explicitly assigned Integration Manager. Personal connections are
owner-visible and remain subject to organization policy. Provider ACLs are authoritative and are
always intersected with Tactiqo grants.

## Repository assessment

OAuth/PKCE, encrypted credential persistence, hostname allowlisting, refresh, discovery, disable,
and tenant/personal visibility already exist. Missing controls are manager authorization, scoped
tool grants, lifecycle transitions, usage/health metadata, revocation, and negative isolation tests.

## Architecture and affected modules

- `integrations/domain`: connection lifecycle and grant values.
- `integrations/application`: manager policy and connection/grant use cases.
- `integrations/infrastructure`: PostgreSQL mappings, scoped queries, MCP gateway filtering.
- API/UI: assignment, lifecycle, health, reconnect, and audit-safe views.

Application ports remain provider-neutral. Adding another provider registers an adapter and does
not change agents or orchestration.

## Data model and migration impact

Connection grants bind a connection/tool to organization, department, team, project, agent, or
user subject and one of read, draft, execute, or administer permissions. Connection metadata adds
last verification, token expiry, consent version, quota, usage, and sanitized failure state.

## API, event, and job contracts

Credentials remain write-only. APIs return connection/grant metadata only. Discovery filters tool
definitions before model context. Calls resolve the connection and effective grants again, so a
revocation takes effect without rebuilding a conversation.

## Security and authorization impact

Server-derived roles and organizational membership are mandatory. Direct identifiers never grant
access. Unknown tools, subjects, revoked connections, missing grants, and ambiguous permissions
fail closed. Mutations continue through the existing approval service.

## Capacity, backpressure, and failure handling

Discovery/calls retain bounded timeouts and result sizes. Per-connection quotas and health prevent
one tenant/provider from exhausting shared capacity. Refresh/reconnect failures move to explicit
expired/error states without returning tokens.

## Human approval

Connection creation, scope/grant expansion, credential rotation, reconnect, and provider revocation
are material configuration operations and require authorized managers; destructive external calls
retain configured run approval.

## Tests, observability, and documentation

Role, tenant, subject, hidden-tool, read/execute, revocation, refresh, result-boundary and secret
redaction tests are required. Audit and metrics contain IDs/reason codes only.

## Open decisions

Production KMS/HSM vendor and billing-plan quota values remain deployment choices. The code uses
ports and policy records so these choices do not require changes to agents or provider adapters.
