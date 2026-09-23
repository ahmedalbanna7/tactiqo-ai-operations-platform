# F10 local observability runbook

Status: operational guidance for the current local/single-API deployment. The thresholds below are
provisional local investigation rules, not approved customer-facing SLOs or production alert policy.

## Safe endpoints

- Liveness: `GET http://127.0.0.1:18000/health/live`
- Readiness: `GET http://127.0.0.1:18000/health/ready`
- Metrics: `GET http://127.0.0.1:18000/internal/metrics`
- Local Prometheus UI (when explicitly started): `http://127.0.0.1:19091` by default; override with
  `TACTIQO_PROMETHEUS_HOST_PORT` if the port is occupied.
- Local operations dashboard: `http://127.0.0.1:13001` by default; override with
  `TACTIQO_GRAFANA_HOST_PORT` if the port is occupied.

Start the local metrics collector with `corepack pnpm stack:observability`. It activates the API,
worker and their core dependencies because Prometheus scrapes both services over the private Compose
network. A one-shot `metrics-auth-init` service creates a random scrape token in the named
`metrics_auth_data` volume if no explicit `TACTIQO_METRICS_AUTH_TOKEN` is configured. API and worker
mount that volume read-only; Prometheus reads the token via its `credentials_file`. The token is not
printed or written to the project `.env`. The collector stores up to 15 days / 2 GB of time series
in the named `prometheus_data` volume. The Prometheus UI and Grafana dashboard bind only to loopback;
Prometheus has no UI authentication configured, so do not expose either service on a LAN or public
interface. Grafana is provisioned as anonymous read-only Viewer for this local profile; its admin
settings endpoint returns 403 to that viewer. Automatic plugin preinstallation is disabled so
startup does not need external plugin downloads. The Prometheus port default was chosen after
`19090` was found occupied on the current host.

The Compose API and worker metrics routes require `Authorization: Bearer <token>`; an unauthenticated
request gets a generic 404. The local Compose token is generated in the Docker volume and supplied
to Prometheus without publishing it. Do not copy it to shell history, screenshots, issue reports or
committed files. `TACTIQO_METRICS_AUTH_TOKEN` remains available for an explicitly provisioned token;
other environments must inject secrets through their secret manager. Keep both endpoints private to
the monitoring network. Worker port 8101 is exposed only to the Compose network and is not mapped to
a host port.

After the observability stack is running, run the deterministic alert-rule unit tests with
`corepack pnpm test:alerts`. These use in-memory Prometheus test series only; they do not enqueue
work or mutate application data.

## Current signals and limitations

The API exports low-cardinality process-local HTTP, AI provider, MCP tool-call, retrieval, ingestion
publish, queue-depth-snapshot and object-storage metrics. Prometheus can persist the samples it
scrapes, but API counters still reset when the API restarts and the current setup does not aggregate
multiple API replicas. Prometheus now evaluates provisional local alert rules, but no Alertmanager
or outbound notification route is configured; inspect `http://127.0.0.1:19091/alerts` manually.

`tactiqo_ingestion_queue_ready_messages` is sampled when the API declares the durable ingestion
queue while publishing. `tactiqo_ingestion_queue_depth_observed_at_seconds` identifies the snapshot
time. This does not count unacknowledged deliveries, is not continuously refreshed, and can become
stale. Never alert on its value without checking the observation time. If no messages are published,
there may be no fresh sample even when a worker is stalled.

The worker exports fixed-label delivery outcome/duration and queue-age histograms, plus worker-owned
object-storage operation outcomes, through its authenticated internal metrics endpoint. These
counters are process-local and reset when the worker restarts. Worker delivery and storage outcomes,
including `queue_age_ms`, are also emitted as allowlisted JSON logs. Legacy deliveries without an
AMQP timestamp produce a `null` queue age. Search logs using fixed event names only; do not copy
payloads, document names, object keys, user/tenant identifiers or exception details into incident
notes. Prometheus collects metrics only; it is not a log aggregator.

## Provisional investigation triggers

These are starting points for a future alert policy and require load-test calibration before
production use:

- **API unavailable:** readiness fails on three consecutive checks, 30 seconds apart. First check
  liveness and container status, then dependency readiness and API logs.
- **Worker scrape unavailable:** Prometheus worker target remains down for one minute. Check that
  the worker container is running, metrics server started with the file-backed token, and RabbitMQ/
  MinIO dependencies are healthy.
- **HTTP errors:** 5xx responses exceed 5% over five minutes with at least 20 requests. Exclude
  intentional authorization denials and inspect route-template/status-class series.
- **HTTP latency:** p95 exceeds 2.5 seconds with at least 20 observations in five minutes. This is
  a local investigation trigger, not a user-facing latency SLO.
- **Provider failures:** failures exceed 20% over five minutes with at least five provider calls.
  Verify configured local/remote provider availability and recent settings changes; never include
  prompts, model secrets or raw exception text in the alert.
- **Ingestion backlog:** ready depth exceeds 50 in two fresh samples at least one minute apart.
  Treat this only as a triage signal: inspect worker running state and sanitized delivery logs. Do
  not infer a stuck queue from an old timestamp or from one point-in-time count.
- **Stale queue sample:** the last publish-time queue-depth sample is older than 120 seconds for one
  minute. The API samples queue depth on publishing only; a stale/missing sample is unknown, not a
  zero-length queue. A restart also resets the API's process-local sample.
- **Worker delivery failures:** more than 20% of at least five observed deliveries fail in five
  minutes. Include retry/dead-letter outcomes in triage, and inspect sanitized logs before deciding
  whether customer documents need recovery.
- **Tool failures:** investigate a sustained failure ratio above 10% over five minutes with at least
  five calls. Distinguish a user-denied/grant-denied operation from an MCP transport failure using
  application audit records, not metric labels.

The HTTP latency/error, provider, tool, API/worker target and queue freshness/depth triggers are
implemented as local Prometheus rules. The thresholds remain provisional and are not
approved SLOs. They do not notify anyone because no Alertmanager route exists. API and worker
counters may reset during a restart and do not aggregate multiple replicas. The provisioned Grafana
dashboard is an at-a-glance local view, not a production/customer dashboard; no-data panels are
expected before the corresponding operation occurs.

## First response checklist

1. Check `docker compose ps` and `/health/live`, then `/health/ready`.
2. If the API recently restarted, account for the reset of process-local counters.
3. Inspect sanitized API JSON completion events and worker events by fixed `event` and `outcome`.
4. For queue incidents, compare depth with its observation timestamp and check whether the worker is
   running; avoid enqueueing synthetic/customer work to test recovery.
5. Preserve database/object data. Do not clear queues, remove volumes, rotate credentials or replay
   production work as an exploratory step; follow the relevant recovery/change approval procedure.
6. Record timeframe, affected service, correlation UUID if present, safe outcome counts, and actions
   taken. Omit payloads, document identifiers, tokens, and raw customer content.

## Incident playbooks

These playbooks are safe local triage guidance, not automated remediation. The checks below are
read-only unless explicitly stated. Any restart, configuration change, credential rotation, replay,
queue operation, migration rollback or data restore requires the service owner to approve the change
and follow the environment's change-control and backup procedure. Do not paste secrets or customer
content into incident notes.

### AI model/provider unavailable or slow

1. Check `/health/ready`, then `docker compose ps`; distinguish API readiness from model readiness.
2. In Settings, verify which provider/model is active and whether the selected local LM Studio model
   is actually loaded, or the configured remote provider is reachable. Check recent sanitized provider
   outcome metrics/log events and the provider's own health status.
3. Compare failure/latency rates with the incident window. A successful API health response does not
   prove that inference is available.
4. Do not include prompts, completions, API keys or raw exception text in a ticket. Switching models,
   changing provider settings or retrying a costly/side-effecting agent run is a change, not a
   diagnostic check; obtain owner approval first.

### Jira/Slack MCP or OAuth connection failure

1. Check the integration's displayed connection/health state and the fixed MCP operation/outcome
   metrics. Use audit records to distinguish a revoked/expired grant or user denial from a transport
   or remote-service failure.
2. Check the provider status page and sanitized service logs. Never print, copy or request OAuth
   access/refresh tokens, authorization headers, or client secrets.
3. Do not repeatedly retry tool calls that can create/update tickets, post messages or trigger
   workflows. Confirm whether a request already took effect in the provider before any approved retry.
   Reauthorization and grant changes require an authorized account owner.

### Prometheus scrape authentication failure

1. Check the Prometheus target's `lastError`, API/worker readiness and whether the expected metrics
   endpoint is reachable from the monitoring network. An unauthenticated host request returning the
   generic 404 is intentional; worker port 8101 is not host-published.
2. Confirm `metrics-auth-init` completed successfully and the API/worker have the read-only
   `metrics_auth_data` mount. Inspect service status and mount metadata only; never read or print the
   token from the Docker volume or environment.
3. The endpoint is fail-closed. Do not disable authentication to restore scraping. Token rotation or
   volume repair requires an owner-approved secret-recovery procedure; this local runbook does not
   define a safe in-place rotation command.

### Ingestion queue backlog or worker delivery failures

1. Verify the queue-depth sample timestamp is fresh; the current signal is publish-time only. Check
   RabbitMQ health, worker status, worker scrape status and sanitized delivery outcomes. Ready depth
   does not include unacknowledged deliveries.
2. Determine whether failures are transient dependency errors, repeated delivery failures, or a
   worker outage using fixed event/outcome values and safe counts. Do not infer an empty queue from a
   missing/stale sample.
3. Do not purge, bulk-requeue, replay or enqueue synthetic/customer work as an exploratory fix. If
   documents may be at risk, preserve queue and object/database state and escalate to the owner with
   timeframe and correlation IDs before recovery.

### Failed deployment or migration

1. Read `docker compose ps`, deployed image/tag or commit, health/readiness, and migration-container
   exit status. Capture the timeline and sanitized logs before changing anything.
2. Preserve database, object-storage and broker volumes. Do not run `docker compose down -v`, delete
   volumes, manually edit migration history, or assume an older application image can use a newer
   schema.
3. A rollback is not just a container restart: confirm schema compatibility and an approved backup
   point, then follow the deployment owner's rollback procedure. If no tested rollback/restore
   procedure exists, stop and escalate rather than improvising.

### Suspected data loss or corruption

1. Record first-observed time, affected service and symptoms using non-sensitive identifiers. Avoid
   exploratory writes or repair commands.
2. Notify the incident owner promptly. Any decision to pause writes or services is an authorized
   incident action; do not independently stop services under this guidance-only procedure.
3. Preserve existing volumes/snapshots and verify backup time, scope and integrity. Before replacing
   anything, test restoration into an isolated environment and validate recovered data there. Never
   restore over the live database or object store without explicit owner approval and a verified
   recovery plan.

For every incident, keep a minimal timeline, affected component, correlation UUID where available,
safe counts and decisions/owners. Exclude prompts, document contents/names, tenant/user identifiers,
object keys, credentials and raw exception details.

## Next production-readiness work

Before adopting these provisional rules as production alert policy: deploy a secured durable
metrics/log backend, support multi-replica aggregation, continuously sample broker depth/age,
validate thresholds under load, configure and test alert delivery, and exercise provider/queue/data
incident runbooks. The local dashboard is not a substitute for production alert delivery or access
control. This document alone does not close F10.
