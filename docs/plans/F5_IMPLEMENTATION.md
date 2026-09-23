# F5 — Durable Worker Agent Runtime

Status: F5 control-plane and extensible worker runtime are operational. Domain processors are
registered incrementally by F7/F8; unknown workloads remain queued and are never faked.

## Implemented

- Job, attempt, lease, checkpoint, progress, artifact, cancellation, and failure models.
- Tenant/actor ownership inherited from the originating run and plan.
- PostgreSQL job ledger with optimistic versioning and append-only sanitized events.
- Tenant-scoped step idempotency and deduplication.
- Expiring exclusive leases, heartbeat tokens, bounded attempts, and retry backoff/jitter.
- Reference-only signed queue messages; input data remains behind platform references.
- Dedicated durable queues and DLQs for document/OCR, media, report/BI,
  integration/automation, and risk-review work.
- F4 Background plans persist a job before RabbitMQ publication.
- Scoped list, detail/progress, and cooperative cancel APIs.
- Registered-processor runtime with bounded concurrency and graceful drain.
- Heartbeats, checkpoint resume, orphan recovery, current-authority revalidation, and
  sanitized bounded retry/DLQ behavior.
- Explicit retry and scope-safe workload metrics APIs.
- Background Jobs UI with live polling, progress, cancel, and retry controls.

## Verified live

- Migration `20260914_0007` applied.
- A Background media request created a durable `media` job and one reference-only queue
  notification.
- `/api/v1/jobs` returned the originating run, plan, step, progress, and version.
- API and worker remained healthy.

## Deferred capability integrations (owned by later domain phases)

- Register real OCR/media/report/BI/integration/risk processors when those execution agents
  arrive in F7/F8; each uses the stable `JobProcessor` port.
- Connect generated MinIO artifacts to the implemented lineage table and production retention
  policy when the first artifact-producing processor is registered.
- Add provider-connection revocation checks inside the integration processor in F6.

Jobs remain queued until their matching domain processor is registered. The platform does not claim
completion or execute an unknown workload with a generic unsafe handler.
