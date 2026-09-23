# F0.2 local infrastructure implementation record

## Scope and assumptions

This increment adds named local service profiles, recoverable local PostgreSQL
and MinIO backups, and deterministic development-tenant seed/teardown commands.
It does not add production backup infrastructure or the F10 telemetry stack.

## Repository assessment and architecture

Docker Compose already owns PostgreSQL, Redis, RabbitMQ, MinIO, API, Web,
Worker, migration, and demo MCP processes. PostgreSQL is the transactional
source of truth and MinIO holds original document objects. The lifecycle CLI is
a development adapter under `scripts/`; it does not move business rules into
API handlers or introduce a second datastore.

## Data, API, event, and job impact

No schema migration, API contract, event, or job contract changes are required.
The deterministic seed creates only a known conversation and welcome message.
Teardown targets rows carrying one explicit development organization ID and
objects under that organization's storage prefix.

## Security, authorization, and approval

- Lifecycle mutation is rejected outside `local`, `development`, or `test`.
- Tenant IDs must start with `dev-` and match a restricted identifier grammar.
- Teardown requires a confirmation value equal to the exact tenant ID.
- Restore requires the exact phrase `RESTORE LOCAL DATA` and a backup manifest.
- Commands never print credentials and never accept production environments.

These commands are local operator tools; they do not bypass application
authorization in a deployed environment because they refuse that environment.

## Capacity, failure handling, and observability

Backups stream PostgreSQL output to disk and copy MinIO objects one at a time to
bound memory. A manifest records time, environment, database artifact, bucket,
object count, and checksums. Commands fail non-zero and retain the prior backup
on partial failure. Restore is operator initiated and intended only for local
test data.

## Tests and documentation

Unit tests cover environment, tenant-name, and confirmation guardrails. Compose
configuration, seed idempotency, tenant-scoped teardown, backup artifacts, and
restore are verified locally. Operating commands are documented in the F0 local
infrastructure runbook.

## Open decisions

Production backup retention, encryption/KMS, object versioning, remote storage,
restore drills, and the telemetry vendor remain F10 decisions.
