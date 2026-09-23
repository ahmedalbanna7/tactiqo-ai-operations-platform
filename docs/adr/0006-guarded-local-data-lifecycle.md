# ADR 0006: Guarded local data lifecycle

- Status: Accepted
- Date: 2026-09-11

## Context

The local platform needs repeatable service subsets and test-data lifecycle
commands. Unscoped teardown or restore commands could erase unrelated tenant
data or connect to a non-local object store.

## Decision

- Use Docker Compose profiles for core, integrations, workers, and local
  observability surfaces.
- Keep PostgreSQL as the transactional source of truth and MinIO as original
  object storage.
- Provide one repository-owned lifecycle CLI for backup, verification, restore,
  deterministic seed, and tenant teardown.
- Reject the CLI outside local/development/test environments.
- Limit tenant teardown to strict `dev-*` identifiers with exact confirmation.
- Require loopback MinIO access and verify archive/object checksums before
  restore mutation.

## Consequences

Local development becomes repeatable and recoverable without adding production
infrastructure or another datastore. Production retention, encryption, remote
backup custody, and disaster recovery remain F10 decisions.
