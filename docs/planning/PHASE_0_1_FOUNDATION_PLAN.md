# Phase 0 and Phase 1 Foundation Plan

Status: proposed for review before implementation.

## 1. Scope

Bootstrap a local-first monorepo and the minimum secure foundation for identity,
organization hierarchy, authorization, audit, industry configuration,
progressive setup, and human-approved configuration candidates.

The phase does not implement production agents, external connectors, Onyx
integration, document extraction, advanced RAG, external actions, Kafka,
Terraform, or Kubernetes.

## 2. Assumptions

- The working repository path is `E:\Tactiqo`.
- `Tactiqo` is a temporary project/repository name and may be renamed later.
- Development is Windows-hosted but Docker Compose is the supported runtime.
- The first deployment remains cloud-neutral until AWS or Azure is selected.
- One dedicated customer exists per deployment; `organization_id` models the
  enterprise/group/legal-entity structure and is not a client-selected SaaS
  tenant key.
- English is used for code and technical documentation. Product localization is
  an open discovery decision.
- The two supplied governing documents are copied unchanged into the repository.
- No real credential or customer data is committed.

## 3. Existing repository assessment

- The original workspace contains an empty Git repository with no commits and no
  application files.
- `E:\Tactiqo` was available at foundation planning time.
- There is no legacy code, schema, migration, or deployment to preserve.
- The source documents currently live outside the repository and need an
  immutable copied baseline under `docs/product/`.

## 4. Proposed architecture and affected modules

Initial form: modular monolith plus separate normal and parsing worker process
entrypoints.

Phase 0/1 modules:

- `shared`: typed configuration, database/UoW, errors, events/outbox,
  observability, security primitives.
- `identity`: users, external identities, roles, permissions.
- `organization`: organization units, hierarchy versions, positions,
  assignments, reporting relationships, delegations, access policies.
- `company_setup`: progressive setup, import sessions, candidates, provenance,
  validation tasks, activation batches.
- `industries`: pack/version metadata, organization/unit/project profiles,
  compiled DomainContext and activation audit.
- `projects`: minimal projects and project membership required for access scope.
- `approvals`: minimal reusable approval policy and decision lifecycle.
- `audit`: append-only security and material-change events.

Other target modules receive boundary placeholders only and no behavior.

## 5. Data model and migration impact

The first migration set will introduce:

- organizations and organization settings;
- organizational units and hierarchy versions;
- positions, assignments, reporting relationships, and delegations;
- users, roles, permissions, role assignments, classifications, clearances,
  grants, and denies;
- projects and project memberships;
- industry pack definitions/versions, organization industry profiles, unit
  activity profiles, project industry profiles, compiled DomainContexts, and
  activation audits;
- setup profiles, import sessions, candidates, candidate provenance,
  validation tasks, approval policies/steps, approval decisions, and activation
  batches;
- audit events, transactional outbox, inbox/idempotency records, and policy
  version fields required by access-cache invalidation.

Every controlled row receives ownership/scope/classification fields where
relevant. Alembic migrations must test upgrade, rollback where practical, and
fresh-database reconstruction. PostgreSQL RLS is defense in depth; repository
filters and application authorization remain mandatory.

The hierarchy read strategy (`ltree` versus closure table) requires an ADR before
the production schema is fixed.

## 6. Initial API, event, and job contracts

Initial synchronous APIs:

- health, readiness, and version endpoints;
- authenticated `/me` and access-context summary;
- organization-unit, position, assignment, reporting, delegation, project, and
  membership commands/queries;
- hierarchy preview, validation, activation, version list, and access explain;
- setup status, candidate review, validation task, activation preview, and
  activation endpoints;
- industry/activity profile preview, activation, and DomainContext query;
- secured audit queries.

Initial domain events/outbox contracts:

- hierarchy version activated;
- assignment/reporting/delegation changed;
- access policy or classification changed;
- configuration candidate materially changed;
- approval granted/rejected/expired;
- industry/activity/project profile activated;
- DomainContext compiled/invalidated;
- activation batch completed/failed.

Initial RabbitMQ jobs, after topology approval:

- outbox dispatch;
- access-context/cache invalidation;
- DomainContext compilation;
- bounded activation batch processing.

All mutation and job contracts include actor/execution scope, version,
correlation ID, idempotency key, and safe error semantics. Payloads carry stable
references rather than secrets or large documents.

## 7. Security and authorization impact

- Derive `AccessContext` only from authenticated identity and active,
  effective-dated server records.
- Apply RBAC, hierarchy, project membership, source/resource ACL,
  classification, grant, and deny policies before every protected query.
- Explicit deny overrides allow.
- Use RLS policies bound to transaction-local, server-set context as defense in
  depth; never trust client scope IDs.
- Version access policy inputs and invalidate caches immediately on hierarchy,
  assignment, delegation, role, grant/deny, or classification change.
- Do not reveal unauthorized resource existence through errors or access
  explanation.
- Store only secret references; redact sensitive values from logs, traces,
  events, prompts, and API output.
- Record sensitive access and every configuration/approval activation in audit.

## 8. Capacity, backpressure, and failure considerations

- API processes are stateless with bounded DB/Redis/broker pools.
- Long or batch work returns a workflow/job ID and runs asynchronously.
- Every queue has bounded concurrency, prefetch, retry budget, DLQ, and oldest
  message/depth monitoring.
- Activation and outbox consumers are idempotent and safely resumable.
- Cache entries include access/configuration versions and explicit TTL and
  invalidation events.
- Database connection budgets and target workload numbers remain open until a
  pilot customer profile is known.
- Normal Phase 1 API target is p95 below 500 ms excluding providers.

## 9. Human approval requirements

Approval is mandatory for:

- hierarchy activation and high-impact hierarchy changes;
- positions/reporting/delegation changes that alter access, according to policy;
- role, permission, classification, clearance, grant, and deny changes;
- organization industry, department activity, project industry, and compiled
  configuration activation;
- imported or AI-extracted configuration candidates becoming official records.

The approval engine supports before/after preview, provenance, affected scope,
comments/edits/rejection, deterministic approver resolution, separation of
duties, stale-proposal expiry, revalidation before activation, immutable audit,
and rollback reference. A candidate cannot approve or activate itself.

## 10. Implementation increments

1. Pin runtimes and tooling; add repository quality configuration and CI.
2. Add local `core` Docker Compose profile for API, web, PostgreSQL, Redis,
   RabbitMQ, MinIO, and test mail service.
3. Document the `knowledge` and `observability` profiles without implementing
   business integration; pin approved component versions when verified.
4. Add typed settings, secret references, logging/trace correlation, database
   lifecycle, health, and readiness.
5. Add shared domain primitives, UoW/repository contracts, audit, outbox/inbox,
   and idempotency.
6. Implement identity and versioned organization hierarchy domain models.
7. Select and implement the hierarchy query strategy after ADR approval.
8. Implement server-derived AccessContext, repository filters, and RLS.
9. Implement minimal projects/project membership and access intersection.
10. Implement industry/setup/approval models and deterministic state machines.
11. Implement preview/activation flows and deterministic DomainContextResolver.
12. Add generated OpenAPI/TypeScript contracts and minimal administration UI
    slices required to exercise the flows.
13. Complete security, migration, integration, API, and architecture tests.
14. Complete runbooks, capacity assumptions, threat model, and exact verification
    report.

Each increment is reviewable and must leave the repository passing its gates.

## 11. Acceptance criteria

- A documented command starts the Phase 0/1 local core without cloud accounts.
- API, web, workers, PostgreSQL, Redis, RabbitMQ, and MinIO expose appropriate
  health/readiness boundaries.
- No committed file contains a real secret.
- The schema is reproducible from Alembic and protected by constraints and RLS.
- A sibling department cannot access another sibling's restricted resources.
- A manager sees only the authorized managed unit and descendants.
- Parent, former-manager, expired-delegation, cross-project, Board, and
  restricted-classification denial cases pass.
- Project access reveals project-authorized data without exposing unrelated
  department data.
- Hierarchy or policy activation immediately invalidates prior access/cache
  versions.
- Access explain returns an authorized, non-leaking reason chain.
- Minimum safe setup can activate while incomplete optional capabilities remain
  visibly unavailable.
- A department cannot activate without a confirmed activity profile.
- A configuration candidate preserves source provenance and cannot activate or
  approve itself.
- Material candidate changes invalidate prior approvals.
- DomainContext is versioned, deterministic, activated by approval, and read at
  runtime without an LLM call.
- Every mutation, approval, and activation is idempotent and audited.
- Formatting, linting, strict typing, unit/integration/security/API/architecture
  tests, migration checks, dependency/secret/container scans, and documentation
  checks pass in CI as applicable to the increment.

## 12. Test plan

- Unit: entities, value objects, policies, state machines, calculations.
- Integration: PostgreSQL constraints/RLS/UoW/outbox, Redis invalidation,
  RabbitMQ retry/DLQ, and MinIO access adapters.
- API: schemas, authentication, idempotency, pagination, error non-disclosure.
- Security: sibling/parent/child/project/manager/delegation/classification,
  grants/denies, privilege changes, and cache isolation.
- Migration: fresh upgrade, upgrade from prior revision, downgrade where safe,
  and representative-data constraints.
- Architecture: module import boundaries and provider SDK placement.
- Failure: duplicate jobs, stale approvals, partial activation, retry exhaustion,
  DB/broker/cache unavailability, and concurrent edits.
- Performance: representative access-context and hierarchy queries plus baseline
  API concurrency after the pilot capacity profile is defined.

## 13. Observability plan

- Propagate request, correlation, causation, actor, workflow, and idempotency IDs.
- Emit structured, redacted logs and OpenTelemetry traces.
- Measure API latency/error/saturation, DB pool/query/lock health, Redis cache
  hit/invalidation, RabbitMQ depth/age/retries/DLQ, worker outcomes, approval
  wait/staleness, and activation results.
- Emit auditable business events without storing secret or unnecessary personal
  payloads.
- Readiness fails when mandatory dependencies prevent safe operation; optional
  provider degradation is reported separately.

## 14. Documentation changes

- Governing product documents copied into the repository.
- System hierarchy, module boundaries, and repository structure.
- ADRs for all approved architecture choices.
- Data/access threat model and authorization explanation.
- API, event/outbox, and RabbitMQ job catalogues.
- Local setup, backup/reset, migration, test, and incident runbooks.
- Exact phase completion and verification report.

## 15. Risks and questions that do not block repository scaffolding

- Pilot industry and first connector are unknown.
- Identity provider and English/Arabic MVP scope are unknown.
- Cloud, hosting ownership, compliance targets, and data residency are unknown.
- Customer capacity, RPO/RTO, and exact SLO targets are unknown.
- Exact models and embedding profile require representative evaluation.

These items do not block the architecture/document scaffold. They do block the
specific implementation that depends on them.

## 16. Approval-gated decisions that block affected implementation

- Hierarchy query model: PostgreSQL `ltree` or closure table.
- RabbitMQ worker framework and topology.
- Exact RAG ingestion/retrieval design and Onyx integration contract.
- Exact agent topology, state, checkpoint, and memory design.
- Model/embedding choices and privacy/data-residency policy.
- Cloud architecture, DR, and managed-service replacements.

No affected implementation starts until its decision is reviewed and recorded.
