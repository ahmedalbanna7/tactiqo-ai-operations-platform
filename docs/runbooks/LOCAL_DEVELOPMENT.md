# Local Development Runbook

## Prerequisites

- Docker Desktop with the Linux engine running
- Docker Compose v2+
- Python 3.12 for host-side backend checks
- Node.js 22 and pnpm 10 for host-side frontend checks

Python 3.14 may be installed on the workstation, but the project must use the
declared Python 3.12 runtime.

## Configure

```powershell
Copy-Item .env.example .env
```

Change every `change-me` value before shared or network-accessible use. The
example values are local placeholders and must never be reused in production.

## Validate configuration

```powershell
docker compose --env-file .env config --quiet
uv sync --frozen --all-groups --extra infrastructure
uv run ruff format --check .
uv run ruff check .
uv run mypy backend/src apps/api/src
uv run pytest -W error
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

Both package managers use committed lockfiles. Docker and CI reject dependency
drift with frozen installation modes.

## Start the local core

```powershell
docker compose --env-file .env up --build -d --wait --wait-timeout 420
docker compose ps
```

Endpoints:

- Web: `http://localhost:13000`
- API: `http://localhost:18000`
- API docs in local mode: `http://localhost:18000/docs`
- PostgreSQL: `localhost:15432`
- Redis: `localhost:16379`
- RabbitMQ AMQP: `localhost:15673`
- RabbitMQ management: `http://localhost:25673`
- MinIO API: `http://localhost:19000`
- MinIO console: `http://localhost:19001`

These host ports are isolated defaults and can be overridden with the
`TACTIQO_*_HOST_PORT` values in `.env`. Internal Compose service ports do not
change.

## Verify

```powershell
Invoke-RestMethod http://localhost:18000/health/live
Invoke-RestMethod http://localhost:18000/health/ready
```

## Stop without deleting data

```powershell
docker compose down
```

Volume deletion is intentionally not included in the normal runbook. A separate
approved reset procedure must verify the exact Compose project and volumes before
removing local state.
