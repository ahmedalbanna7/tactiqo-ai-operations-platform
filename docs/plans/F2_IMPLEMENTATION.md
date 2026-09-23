# F2 Authorization Policy Compiler and Agent Catalog

## Scope and assumptions

F2 introduces one server-side decision point for agent discovery and invocation.
RBAC grants are narrowed by organization relationships and ABAC conditions. Missing
or conflicting information denies access. Prompt text never grants permission.

## Repository assessment

F1 provides immutable actors, organization hierarchy, current execution-context
reconstruction, roles, memberships, step-up assurance, and policy versions. Existing
tool authorization is deliberately small and will remain as a risk classifier while
the F2 compiler becomes the authority for agent visibility and actions.

## Architecture and affected modules

- `authorization/domain`: policy vocabulary, decisions, conditions, obligations.
- `authorization/application`: versioned compiler and audit/cache ports.
- `authorization/infrastructure`: PostgreSQL rules, decision audit, and safe cache.
- `agents/catalog`: versioned catalog, organization lifecycle, assignments, and
  effective card projection.
- API: effective-card discovery and guarded direct invocation contracts; Owner/Admin
  catalog administration.

## Data and migrations

PostgreSQL remains authoritative. F2 adds policy rules and decision audit; agent
definitions/versions; organization installations; assignments; separate action
grants; scope bindings; connection/tool attachments; quotas/budgets; and approval
chains. Every tenant-owned foreign key includes the organization boundary.

## API, event, and job contracts

Employee responses contain effective cards and allowed actions only. Hidden agents,
assignments, departments, rules, and denial internals are never returned. Every run
or resume calls the compiler again using current F1 context and policy version.

## Security and authorization

Explicit deny wins, otherwise a matching allow is required. Classification,
department, team, project, geography, time, ownership, role, and user relationships
can narrow a grant. Obligations include approval, redaction, rate/quota, and step-up.
Decision audit is sanitized and excludes prompt, document, credential, and token data.

## Capacity and failure handling

Only allow decisions may be cached, with a bounded TTL and keys containing actor,
membership scopes, resource, action, and policy version. Repository/cache failure
denies. Policy-version or membership changes produce a different key immediately.

## Human approval

High-risk actions may compile to an allow decision with an approval obligation; the
existing durable approval subsystem remains responsible for the human decision.

## Verification and documentation

Matrix, explicit-deny, hidden-discovery, direct-invocation, revocation, cache
invalidation, obligation, API projection, migration, lint, typing, and container
checks are required before closure.

## Open decisions

No blocking product decision. Initial policies and agent packs are conservative
defaults and can be extended additively through versioned records.

## Closure evidence

F2 closed on 2026-09-12. The versioned PostgreSQL migration is at head
`7b285f2ac567`; 22 initial packs are installed for the local organization; the
employee projection returns 22 effective cards and hides denied agents behind the
same not-found response. A live LangGraph chat run completed through the Planner
authorization gate. Explicit-deny creation/revocation, policy-version invalidation,
and install disable/enable were exercised against the running API.

Approval chains are configurable by Owner/Admin through
`PUT /api/v1/agent-catalog/approval-chains` and are selected by agent, action, risk,
and target system. The live PostgreSQL check stored the ordered chain and emitted a
sanitized audit event containing only selector metadata and step count.

Final automated gates: Ruff, mypy over 124 source files, 78 Python tests, frontend
ESLint, and the Next.js production build. Runtime containers report healthy for the
API and its core dependencies.
