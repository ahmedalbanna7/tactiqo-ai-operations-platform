# Health and Readiness Endpoints

## `GET /health/live`

Confirms only that the API process can serve requests. It does not call external
dependencies and must remain suitable for container liveness probes.

## `GET /health/ready`

Runs bounded checks against mandatory core dependencies:

- PostgreSQL
- Redis
- RabbitMQ connectivity only; it declares no topology
- MinIO liveness

The endpoint returns HTTP `503` when any mandatory dependency is unavailable.
Provider exception text, credentials, URLs, and stack traces are never returned.
Every response contains a validated `X-Correlation-ID` header.

Onyx, model providers, and external connectors are excluded until their phases
and degraded-mode policies are approved.
