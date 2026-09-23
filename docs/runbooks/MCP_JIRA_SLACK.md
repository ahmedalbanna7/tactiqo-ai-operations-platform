# Jira and Slack MCP connections

## SaaS runtime model

Jira and Slack are tenant-managed integrations. An organization account manager
can add an organization-wide connection, while an end user can add a personal
connection. The API derives the organization and actor from the authenticated
execution context; clients cannot submit either identifier.

Credentials are encrypted at rest, never returned by the API, and resolved only
for the tenant and actor allowed to use the connection. Disabling a connection
soft-deletes it and erases the encrypted credential. Every MCP tool is qualified
with its provider and connection id so one tenant can safely use multiple Jira
or Slack accounts.

The UI uses provider OAuth by default. It creates a PKCE S256 authorization
request, validates a signed ten-minute state at callback, exchanges the code,
and stores access/refresh tokens as one encrypted credential envelope. Tokens
are refreshed shortly before expiry. Manual `Bearer` or `Basic` authorization
remains available under the advanced account/service-token option.

## Platform configuration

Generate one Fernet key per deployment and keep it in the platform secret
manager. Never expose it to tenants or commit it to source.

```dotenv
TACTIQO_INTEGRATION_CONNECTIONS_ENABLED=true
TACTIQO_CREDENTIAL_ENCRYPTION_KEY=<fernet-key>
TACTIQO_OAUTH_PUBLIC_API_BASE_URL=http://127.0.0.1:18000
TACTIQO_OAUTH_WEB_BASE_URL=http://127.0.0.1:13000
TACTIQO_SLACK_OAUTH_CLIENT_ID=<slack-app-client-id>
TACTIQO_SLACK_OAUTH_CLIENT_SECRET=<slack-app-client-secret>
```

Jira uses the MCP server's Dynamic Client Registration endpoint, so no static
Jira client secret is required. Slack requires an app Client ID and Client
Secret. Register the exact local redirect URL
`http://127.0.0.1:18000/api/v1/integrations/oauth/slack/callback` in that app.
Production must use the public HTTPS API origin and its matching callback.

Allowed provider endpoints are fixed by the backend:

- Jira: `https://mcp.atlassian.com/v2/mcp?tools=all`
- Slack: `https://mcp.slack.com/mcp`

The hostname allowlist prevents tenants from turning the connector into an SSRF
proxy. Provider-side plans, admin consent, scopes, and MCP availability still
apply.

## API workflow

1. `POST /api/v1/integrations/connections` creates an encrypted personal or
   organization connection.
2. `POST /api/v1/integrations/oauth/{provider}/start` starts OAuth consent;
   `/callback` completes it without exposing tokens to the browser.
3. `GET /api/v1/integrations/connections` lists only connections visible to the
   current organization and actor, without credentials.
4. `POST /api/v1/integrations/connections/{id}/verify` performs MCP discovery
   and returns the discovered tool count.
5. `DELETE /api/v1/integrations/connections/{id}` disables the connection and
   erases its credential.
6. `PUT /api/v1/integrations/connections/{id}/grants` assigns an explicit subject,
   tool, and read/draft/execute/administer capability. Connections expose no tools
   until at least one effective grant exists.
7. `POST /api/v1/integrations/connections/{id}/revoke` immediately blocks use and
   erases local credential material. `PUT .../{id}/credential` performs a write-only
   reconnect or rotation and returns the connection to active state.

## Credential rotation

Use provider OAuth reconnect where available. For service credentials, create the new
provider token first, update the connection through the write-only credential endpoint,
verify discovery, then revoke the old provider token. Production encryption keys are
rotated by a KMS/HSM-backed `CredentialCipher` adapter; never copy plaintext credentials
through database migrations, logs, support tickets, or browser responses.

Agents resolve connections for every run from the execution context. Provider
ACLs remain authoritative. Mutating tools still pass through Tactiqo policy,
approval, and audit controls before execution.

## Production checklist

1. Replace the local development identity provider with production SSO/JWT and
   map account-manager roles to organization-connection administration.
2. Verify one read-only operation and one approval-gated mutation in non-production
   Jira and Slack workspaces.
3. Confirm tenant isolation, personal-connection isolation, audit redaction, key
   rotation, revocation, and provider token expiry behavior.

The legacy single-connection environment variables remain for local compatibility
only; new SaaS deployments should use database-backed connections.
