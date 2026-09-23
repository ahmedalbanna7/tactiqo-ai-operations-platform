# F10 implementation record

Status: active. F10 now hardens the currently implemented platform; it does not certify production
release and does not imply completion of deferred F7/F8/F9 product gates. Those requirements are
tracked under F11 in `MASTER_IMPLEMENTATION_PLAN.md`.

## F10.1 — Safe structured HTTP telemetry

- Added JSON completion events for each HTTP request with an explicit field allowlist: UTC timestamp,
  level, fixed event name, correlation ID, HTTP method, route template, status code and duration.
- Raw URL/query strings, request/response bodies, headers, authorization values, tenant/user IDs,
  exception messages and stack traces are not serialized by the HTTP telemetry formatter.
- Route templates are used instead of concrete paths so document, connection and user identifiers
  in path segments are not copied into this log event.
- Correlation ID is taken from the validated response header. If none was emitted, the log uses the
  literal `unavailable` rather than reflecting an untrusted request value.
- Tests cover strict formatter allowlisting and a request containing a secret query value; neither
  the test credential nor raw query is present in the emitted JSON event.

## F10.1 — Bounded HTTP metrics

- Added process-local Prometheus text exposition at `/internal/metrics`: request counter plus latency
  histogram with fixed buckets, grouped only by allowlisted method, route template and status class.
- Metric series never include tenant/user/document IDs, query strings, request data or provider names.
  Unknown HTTP methods collapse to `OTHER`; concrete path values are replaced by route templates.
- A configured `TACTIQO_METRICS_AUTH_TOKEN` requires constant-time Bearer-token comparison. Without
  a token the endpoint is available only for `local`, `development` and `test`; other environments
  return a generic 404. Production deployment must inject a dedicated scrape token through its
  secret manager, not commit it to `.env.example`.
- Metrics are process-local and reset on restart; a shared multi-replica backend/exporter and worker,
  provider, MCP, retrieval, queue and storage instrumentation remain future F10 work.

## Verification

- Focused observability tests now cover JSON redaction, route-template/cardinality bounds, histogram
  counters, token-required scraping, and fail-closed behavior outside development.
- Full repository suite after HTTP telemetry, metrics, and F9 authorization additions: 200 passed.
- Ruff passes for observability module, API composition and observability tests.
- `git diff --check` passes; no frontend source changed in F10.1.
- Docker API and migration images rebuilt successfully. Local scrape returned HTTP 200 with the
  expected counter and histogram series; live health returned 200 plus a correlation ID, readiness
  reported healthy, and all Compose services were healthy/running.
- Mypy was attempted but did not complete within this Windows runtime window; no pass is claimed.

## F10.2 — Ingestion-worker delivery telemetry

- The isolated worker logger now emits one compact JSON completion event with fixed component,
  operation and event names; `outcome`, bounded `retry_count` and elapsed `duration_ms` are the only
  delivery values included.
- The formatter discards the log message and arbitrary `LogRecord` fields. Delivery payload, message
  ID, document ID, tenant/user IDs, envelope, provider error and secrets are not logged. The
  correlation ID is included only after signed-envelope verification and is canonicalized as a UUID;
  missing/invalid values become `unavailable`.
- ACK, retry publication and DLQ behavior are unchanged. Telemetry is emitted after each handled
  delivery outcome and is not used to decide processing state.
- Unit tests cover formatter allowlisting/bounds and a successful `_handle` path, including proof
  that document and message identifiers do not appear in the event.
- Verification: Ruff passes; full repository suite is 203 passed; `git diff --check` passes.
- Docker worker image rebuilt and service restarted. Worker is Up with PostgreSQL, RabbitMQ and
  MinIO healthy. No synthetic document was enqueued, so no business-data ingestion was performed.

## F10.3 — Signed correlation propagation into ingestion telemetry

- Reused the correlation ID already carried by the signed work envelope; no queue schema, API,
  migration, or signature contract changed.
- The worker sets the value only after `WorkEnvelopeSigner.verify` succeeds. Its log formatter
  independently canonicalizes UUIDs and maps missing or invalid values to `unavailable`.
- Correlation IDs appear only in logs, never as Prometheus labels. Tenant, user, document and message
  identifiers remain excluded.
- Tests cover valid and invalid correlation formatting, plus the successful worker delivery path;
  existing work-envelope tests continue to cover signature tampering and expiry.
- Verification: Ruff passes, full repository suite is 203 passed, and `git diff --check` passes.
  Worker image rebuilt and restarted; API, worker, PostgreSQL, RabbitMQ and MinIO are running
  (dependencies report healthy; worker has no configured healthcheck). No synthetic ingestion was
  enqueued.

## F10.4 — Bounded LLM and embedding provider metrics

- `AIBank` records one outcome and latency observation for each actual provider attempt. Retries and
  fallbacks are observed separately, while requests rejected before reaching an adapter are not
  counted as provider calls.
- The protected `/internal/metrics` exposition now combines HTTP and provider metrics. Provider
  labels are fixed to `lm_studio`, `openai`, `claude` or `other`; operation to `llm_plan`,
  `llm_answer`, `embedding` or `other`; and outcome to `success` or `failure`.
- No tenant, actor, profile, model, endpoint, prompt, embedding content or raw exception is present
  in provider series. The registry is process-local and bounded; it resets on restart and is not a
  replacement for durable usage accounting already performed by the profile repository.
- Tests cover successful/failed bank routing, label/cardinality sanitization, and combining HTTP plus
  provider exposition at the authorized scrape route. Ruff passes and the full repository suite is
  204 passed; `git diff --check` passes.
- API and worker images rebuilt and restarted. Local `/internal/metrics` returned HTTP 200 and
  included both HTTP and provider metric families. No external LLM or embedding provider was called.

## F10.5 — Bounded MCP tool-call metrics

- Wrapped the composed tool gateway after its tenant resolution and authorization-aware adapters,
  so only calls that reach the gateway boundary are measured. Tool discovery is not counted.
- Each call contributes a result and duration; thrown transport errors and MCP `is_error` results
  are failures. Tool selection, grant checks, approval and audit behavior remain unchanged.
- Metric labels are restricted to `slack`, `jira`, `confluence`, `demo` or `other`, plus
  `success`/`failure`. Tool names, connection IDs, arguments, results, URLs, tenant/user IDs and
  credentials are excluded.
- Metrics are appended to the same authenticated/process-local `/internal/metrics` endpoint.
  Isolated unit tests verify result passthrough and redaction. Ruff passes, full repository suite is
  206 passed, and `git diff --check` passes.
- API image rebuilt and healthy. Local `/internal/metrics` returned HTTP 200 and contained HTTP,
  AI-provider and tool-call metric families. No customer-connected MCP call was executed.

## F10.6 — Retrieval outcome and latency metrics

- The fallback boundary records `search` and `list_sources` operations with outcomes `primary`,
  `fallback` or `failure`, plus fixed-bucket duration histograms.
- Metrics omit query text, source names, citations, document IDs and tenant/user identifiers. The
  existing fallback behavior and ACL/content-security processing remain unchanged.
- Tests verify primary and fallback paths and ensure query/customer data is absent from exposition.
  Ruff passes, full repository suite is 208 passed, and `git diff --check` passes.
- API image rebuilt and reached healthy. Local `/internal/metrics` returned HTTP 200 and exposed the
  retrieval family together with HTTP, AI-provider and tool-call metrics.

## F10.7 — Ingestion publish and worker delivery outcomes

- The API publisher now records only `success`/`failure` and publish duration after RabbitMQ's
  publisher-confirm call. Queue name, broker URL, document/message IDs, envelope and tenant data
  are excluded from its Prometheus series.
- The worker retains sanitized delivery completion events for `processed`, `retry_scheduled`,
  `dead_letter` and `failed`; tests exercise successful processing, retry scheduling and DLQ paths.
  Correlation is included only after signed-envelope verification.
- ACK, republish, DLQ, publisher-confirm, and canonical database/storage semantics are unchanged.
- Unit tests use mocked RabbitMQ connections and do not enqueue documents. Full suite, API/worker
  tests also cover worker retry and DLQ log outcomes without identifiers. Ruff passes, the full
  repository suite is 212 passed, and `git diff --check` passes.
- API image rebuilt and healthy; worker source/image did not change in this increment, and its
  existing container remains running. Local scrape returned HTTP 200 with HTTP, AI, MCP, retrieval
  and ingestion-publish metric families. No synthetic document was enqueued.

## F10.8 — API object-storage outcomes and latency

- `MinioObjectStorage` records fixed `put`, `get` and `delete` operations as success/failure plus
  latency. The API composition supplies a process-local registry exposed through protected
  `/internal/metrics`.
- Storage keys, tenant prefixes, bucket/endpoint, credentials, content type, checksums, byte counts,
  payloads and provider exception messages are not metric labels or values.
- Object results, response cleanup and storage exception propagation are unchanged. Unit tests use a
  fake MinIO client; no real object was written/read/deleted for verification.
- Current scope: API-owned storage operations are scraped. Worker-owned per-operation metrics are
  not scraped because the worker has no authenticated metrics endpoint; its delivery completion
  logs still provide overall ingestion duration/outcome. Worker now also emits fixed-field JSON
  per-operation storage events; logs do not provide scrapeable process-local worker counters.
- Newly published ingestion messages carry the AMQP timestamp. The worker logs bounded `queue_age_ms`
  alongside delivery outcomes and preserves the original enqueue timestamp across retry republishing.
  Legacy messages without a timestamp emit `null`; queue age is diagnostic only and does not affect
  processing decisions.
- Full suite is 215 passed; Ruff and `git diff --check` pass. API and worker images rebuilt; API is
  healthy and worker is running. Local scrape returned HTTP 200 with the object-storage family.
  No real object operation or synthetic ingestion was run for verification.

## Remaining F10 work

- Durable/multi-replica aggregation, continuous broker depth/age, cross-process traces and metrics
  for remaining storage/provider paths. Queue depth is currently sampled by the API publisher and
  is process-local; queue age is exported by each worker as a process-local histogram.
- Dashboards, SLOs, alerts, threat model/security baseline, key custody, deployment environments,
  migration/rollback, backup/restore and operational exercises.

## F10.9 — RabbitMQ ready queue depth gauge

- The existing durable queue declaration already returns RabbitMQ's ready-message count; the API
  records that snapshot as the fixed gauge `tactiqo_ingestion_queue_ready_messages` and exports the
  snapshot time as `tactiqo_ingestion_queue_depth_observed_at_seconds` through the existing protected
  metrics endpoint. No queue name, tenant, document, message or credential labels are emitted.
- It is a point-in-time, API-process-local snapshot sampled during publishing—not a continuously
  refreshed broker metric. Consumers can reduce the count immediately after sampling, and no later
  publish means the sample becomes stale; alerting must account for the observation timestamp.
- No management port, exporter, schema, queue behavior, or worker listener was added. Invalid counts
  are ignored, negative counts clamp to zero, and extreme values are bounded.
- Tests cover count capture, exposition and sanitization. Full suite passed (216 tests), Ruff and
  `git diff --check` pass; rebuilt API is healthy and local readiness and scrape return HTTP 200.
  No ingestion message was published to generate/verify a real queue-count sample.

## F10.10 — Observability runbook baseline

- Added `docs/runbooks/F10_OBSERVABILITY.md` with endpoint access controls, current metric families,
  process-local/reset and stale-snapshot caveats, provisional (not deployed) investigation triggers,
  and a safe first-response checklist.
- It explicitly prohibits treating the queue gauge as current without checking its observation time
  and documents that worker outcome/age remain logs, not scrapeable metrics.
- This is a local operational guide only. Durable aggregation, dashboards, alert rules and the other
  F10 provider/security/deployment runbooks remain incomplete.

## F10.11 — Local Prometheus collection

- Added a profile-gated, digest-pinned Prometheus service which scrapes API metrics over the private
  Compose network every 15 seconds. Its UI binds to loopback and its named volume is bounded by
  15-day and 2-GB retention limits. The helper command targets Prometheus and activates its API/core
  dependencies without starting the unrelated worker profile.
- Prometheus persists samples across API restarts, but source counters remain per-process and this
  single-target setup does not aggregate multiple API replicas. Queue depth remains a publish-time
  snapshot; worker logs are still not scraped. No Grafana dashboards, Alertmanager routes, or external
  remote-write destinations are configured.
- Official configuration supports the current static scrape target and private endpoint. Do not
  enable the monitoring profile in a nonlocal environment unless its API scrape token is securely
  provisioned; otherwise the API correctly returns 404 to Prometheus.
- Verification: `docker compose --profile core --profile observability config --quiet` passes;
  Prometheus reports healthy (HTTP 200 at `/-/healthy`) and the `tactiqo-api` scrape target is `up`.
  Host port 19090 was already occupied, so the configurable loopback default is 19091; the existing
  process on 19090 was left untouched.

## F10.12 — Provisional local alert evaluation

- Prometheus now evaluates local rules for API scrape availability, API 5xx ratio, AI-provider
  failure ratio, MCP tool-call failure ratio, and a fresh high ready-queue sample. Rules use
  aggregate expressions and static alert labels; no tenant, document, tool name, model or exception
  data is added to alerts.
- The thresholds are investigation triggers only, based on low local traffic and not load-tested.
  Queue-depth alerting requires a fresh snapshot and can clear when the snapshot becomes stale.
- No Alertmanager or notification receiver was added. Alerts are visible only in the local Prometheus
  UI; do not describe them as notifications or production SLOs.
- Prometheus validates the configuration and all five rules with `promtool`; its rules API reports
  all five loaded and both Prometheus/API scrape targets are `up`. `git diff --check` passes.

## F10.13 — Authenticated worker metrics in local Prometheus

- Added bounded process-local delivery outcome/duration and queue-age histograms, and worker-owned
  object-storage outcomes/duration, on a dedicated `/internal/metrics` server. Labels use only fixed
  operation/outcome values; no tenant, user, document, queue, key, object, or customer-content values
  are included.
- Metrics use constant-time Bearer-token verification. Compose creates one random token in a named
  Docker volume if no explicit token is configured; API and worker mount it read-only and Prometheus
  consumes it through `credentials_file`. The token is never written to `.env` or printed. Worker
  port 8101 is Compose-network-only and has no host port mapping.
- `stack:observability` now includes the worker profile, so it starts the API, worker and required
  dependencies before Prometheus. JSON worker logs remain separate; Prometheus collects metrics, not
  logs.
- Verification: focused observability tests (17 passed), Ruff checks passed, full suite (222 passed),
  Docker API/worker images built, Compose configuration validated, API healthy, Prometheus healthy,
  and API/worker/Prometheus scrape targets reported `up`. Unauthenticated API metrics returned 404;
  worker port has no host mapping. No customer document or synthetic ingestion was submitted.

## F10.14 — Local Grafana operations dashboard

- Added a version-controlled Prometheus datasource, file-provisioned dashboard and Grafana service
  in the opt-in `observability` profile. The dashboard covers API/worker scrape status, HTTP request
  rate and 5xx ratio, AI/MCP/retrieval outcomes, ingestion queue depth and sample age, worker delivery
  outcome and queue age, and object-storage operations.
- Grafana image is pinned by digest. The UI binds to loopback only, disables sign-up/login form, and
  grants anonymous Viewer access only for local observation; do not expose this local profile to a
  LAN or public network. Automatic plugin preinstallation and plugin administration are disabled,
  avoiding startup-time plugin downloads. Dashboard definitions and datasource are read-only
  provisioned from source.
- `corepack pnpm stack:observability` now starts Grafana as well as Prometheus/API/worker dependencies.
  The UI is at `http://127.0.0.1:13001` by default (`TACTIQO_GRAFANA_HOST_PORT` overrides the port).
- Dashboard panels distinguish no samples from zero activity, especially for worker deliveries and
  publish-time queue snapshots. No synthetic/customer work was enqueued to populate panels.

## F10.15 — Worker and freshness investigation triggers

- Added local Prometheus rules for authenticated worker scrape availability, stale publish-time
  queue snapshots, worker delivery failure ratio, and API request p95 latency. Existing queue-depth,
  HTTP error, provider and tool rules remain in place.
- Extended the Grafana board with a clear queue-sample-missing indicator, API p95 latency and worker
  delivery failure ratio. Queue snapshot age remains separate because an absent sample and an old
  sample are different operational states.
- All thresholds are provisional investigation triggers. Worker failure/latency rules wait for
  minimum sample counts; queue depth is still publish-time only and stale/missing must never be
  interpreted as an empty queue. No documents or synthetic ingestion were submitted.
- Verification: `promtool check rules`, Prometheus rules API reports the new rules loaded, Grafana
  dashboard provisioning updates, and all 15 dashboard PromQL queries validate. Anonymous Viewer
  access can read the dashboard but receives HTTP 403 from Grafana admin settings; Grafana and
  Prometheus are published only on loopback. This is not a load test and does not make the thresholds
  approved SLOs or notification routes.

## F10.16 — Deterministic alert-rule unit tests

- Added `infra/otel/alerts.test.yml` and the `corepack pnpm test:alerts` helper. `promtool test rules`
  checks expected firing and no-premature-fire cases for worker scrape availability, queue snapshot
  freshness/backlog, worker delivery failures, API p95 latency and API 5xx ratio.
- Tests use synthetic in-memory Prometheus series only. They do not call the API, enqueue tasks,
  write customer data, or send notifications.
- Verification: all rule tests pass, all nine rule definitions pass `promtool check rules`, and
  `git diff --check` plus Compose config validation pass. These tests improve rule correctness but
  do not calibrate thresholds under real load or prove Alertmanager delivery.

## F10.17 — CI gate for alert rules

- Added a separate backend CI job using the digest-pinned Prometheus image to run `promtool test
  rules` and `promtool check rules` against the repository files. CI does not need a running Tactiqo
  stack, secrets, or customer data.
- The equivalent local package script passed. The remote CI job will execute on the next push or pull
  request; no claim is made that hosted CI passed in this local session.

## Next bounded increment

## F10.18 — Incident triage playbooks

- Expanded the local runbook with scoped read-only triage for AI provider/model outages, Jira/Slack
  MCP and OAuth failures, Prometheus scrape authentication, ingestion backlog/worker failures, bad
  deployment/migration, and suspected data loss/corruption.
- Explicitly marks restarts, configuration/credential changes, retries of mutating tool calls,
  queue operations, rollback, pausing writes and restore-over-live as owner-approved actions. The
  guidance forbids exposing secrets/customer data and destructive volume/queue shortcuts.
- Updated the master plan: runbook guidance exists, but executable rollback, tested backup/restore
  and incident exercises remain open. No production incident action or recovery exercise was run.
- Verification is documentation-only; application tests were not rerun because no application code
  changed.

## F10.19 — Local backup/restore runbook alignment

- Reviewed `scripts/local_data.py` and documented its actual behavior: the backup covers the
  configured PostgreSQL database and MinIO bucket; verification checks checksums and PostgreSQL
  archive readability but is not a restore drill; restore can replace database objects and removes
  every current object in the configured bucket before copying the selected backup.
- Added local preflight guidance for target identity, free space, sensitive backup custody, verifying
  a fresh pre-restore backup, application/worker writes, and post-restore health checks. Clarified
  that `.local/` is Git-ignored but not encrypted or off-host by that fact.
- No backup or restore command was run and no database, bucket, Docker volume, or customer data was
  changed. Production backup retention, encryption, off-host storage, isolated restore exercises,
  RPO/RTO, and automatic recovery remain open.
- Verification: focused local-data safety tests pass (11 tests) and the full repository suite passes
  (222 tests); `git diff --check` and the Compose configuration check pass. No backup/restore
  command was run and no application data was changed.

- Load-test/calibrate provisional triggers; then address durable multi-replica aggregation,
  continuous broker signals, threat model/secret custody and the remaining deployment,
  backup/restore and operational exercises before closing F10.

No production release is permitted until F10 operational gates and F11 deferred F7/F8/F9 gates pass.
