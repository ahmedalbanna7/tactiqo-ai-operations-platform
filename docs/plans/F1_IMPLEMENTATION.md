# F1 production identity and organization hierarchy implementation record

## Scope and assumptions

F1 replaces browser-supplied/local identity outside development with generic
OIDC Authorization Code + PKCE, immutable provider-subject mapping, revocable
server sessions, and tenant-scoped organization hierarchy. The first adapter is
provider-neutral OIDC so Entra ID, Auth0, Keycloak, or another conforming IdP can
be added through configuration. SAML is supported through an OIDC-capable
identity broker rather than a second authorization model.

## Architecture and affected modules

Identity uses domain values, application ports/services, and infrastructure
adapters. Organization hierarchy remains in the modular monolith and PostgreSQL.
HTTP handlers receive only a server-reconstructed `ExecutionContext`.

## Data, API, events, and jobs

The phase adds users, sessions, auth audit, organizations, invitations,
memberships, role definitions/assignments, departments, teams, projects, and
scoped membership tables. Revocation changes the membership/policy version so
resumed streams, graphs, approvals, and workers must reconstruct context.

## 2026-09-11 implementation checkpoint

- Implemented generic OIDC Authorization Code + PKCE login and callback.
- Implemented opaque server sessions with rotation, revocation, replay protection,
  listing, logout, and secret-safe audit events.
- Added tenant-scoped department, team, project, and privileged-role APIs.
- Added signed, expiring worker envelopes that contain minimum authorization scope
  and never contain browser sessions or provider credentials.
- Wired document ingestion publishing and worker consumption to the signed envelope;
  document lookup is tenant/scope constrained.
- Enforced startup rejection of local development identity in staging and production.
- Verification: Ruff, Mypy, 60 Pytest tests, Compose validation, API readiness, and
  container startup all pass.

## F1 closure — 2026-09-11

F1 is closed. The remaining exit work was completed as follows:

- Workers verify the signed minimum envelope and then reconstruct current database
  authority; suspended users, tenants, expired memberships, and revoked roles fail
  closed before document access.
- Local development now provisions a real UUID Owner, organization membership, and
  Owner role after migrations. Shared environments cannot enable that bootstrap.
- Department, team, and project membership APIs derive the tenant from the server
  context. Team membership requires current membership in the owning department;
  project matrix membership does not add department visibility.
- Team managers must belong to the owning department. Project managers must be an
  active member of the same organization.
- Owner transfer, suspension, export, retention, and deletion are durable lifecycle
  requests. They require step-up authentication and a different approver. Suspension
  revokes tenant sessions immediately; deletion enters `deletion_pending` until its
  explicit retention deadline instead of deleting data synchronously.
- Platform provisioning creates immutable provider subject mapping, organization,
  active Owner membership, and Owner role atomically.
- Privileged and lifecycle audit records contain safe before/after values and no raw
  claims, browser cookies, access tokens, or refresh tokens.

Closure evidence:

- Ruff passed.
- Mypy passed over 103 source files.
- Pytest passed: 67 tests.
- ESLint, TypeScript, and the Next.js production build passed.
- Real PostgreSQL/API hierarchy flow created department, team, and project records.
- Real API/RabbitMQ/worker ingestion reached `ready` with the `unstructured` parser.
- A real lifecycle self-approval returned HTTP 409 and remained `pending` in
  PostgreSQL.

## Security and approvals

OIDC validation requires asymmetric signatures, exact issuer/audience, expiry,
issued-at, nonce, JWT type, token ID, and replay prevention. Email is profile
data only, never authority. Owner transfer and privileged role changes require
step-up authentication, separation of requester/approver, and durable audit.

## Capacity, failure handling, tests, and observability

JWKS and membership resolution are bounded and fail closed. Sessions are opaque,
hashed at rest, revocable, and listed without secrets. Tests cover invalid
tokens, replay/revocation, tenant hierarchy isolation, scope inheritance,
privilege escalation, IDOR behavior, and production startup safety.

## Open external configuration

Real login requires OIDC issuer, client ID/secret, audience, redirect URI, and
provider-side callback registration. These values are deployment configuration,
not source code and do not block deterministic security tests.
