# ADR 0007: Generic OIDC and server-reconstructed execution context

- Status: Accepted
- Date: 2026-09-11

## Decision

Tactiqo uses generic OIDC Authorization Code with PKCE as its first production
identity boundary. SAML deployments use an OIDC-capable identity broker. The
provider subject maps to an immutable internal user; email is never authority.

Every request resolves an opaque, hashed, revocable session against current
organization/member/role/department/team/project state. Browser-supplied tenant
or scope fields are ignored. Privileged assignments require an Owner, MFA or
step-up assurance, a different target user, and tenant-predicated persistence.

## Consequences

The same domain and authorization model works with Entra ID, Auth0, Keycloak,
and conforming providers. Revocation is observed when context is reconstructed,
and no provider token or raw claims enter logs, queues, prompts, or API output.
