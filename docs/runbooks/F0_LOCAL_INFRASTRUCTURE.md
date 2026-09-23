# F0 local infrastructure runbook

## Named stacks

```powershell
corepack pnpm stack:core
corepack pnpm stack:integrations
corepack pnpm stack:workers
corepack pnpm stack:observability
corepack pnpm stack:all
```

`core` starts the databases, API, and Web. `integrations` starts the demo MCP
adapter. `workers` starts the durable worker and its dependencies.
`observability` exposes the existing local infrastructure health and management
surfaces; the production telemetry stack is deliberately scheduled for F10.

## Deterministic development tenant

Run commands from the repository root. The organization must start with
`dev-`; repeated seed commands are idempotent.

```powershell
uv run python scripts/local_data.py seed --organization-id dev-tactiqo
uv run python scripts/local_data.py teardown --organization-id dev-tactiqo --confirm dev-tactiqo
```

Teardown removes only rows and MinIO keys owned by that exact organization.

## Local backup and restore

These commands are development/local lifecycle tools, not a production backup service. Run them
from the repository root with the intended local Compose stack active. Backups contain the entire
configured PostgreSQL database and MinIO bucket, so treat the output as sensitive company data.
`.local/` is ignored by Git; still confirm the chosen output path is on a protected disk with enough
free space, and never commit, email, or place the backup in a public/shared folder. Encryption,
off-host custody, retention scheduling, and point-in-time recovery are not implemented here.

### Create and verify a local backup

```powershell
uv run python scripts/local_data.py backup
uv run python scripts/local_data.py verify --backup .local/backups/<timestamp>
```

The command prints the created path. Keep that exact path for verification. Verification checks the
manifest, PostgreSQL archive readability, configured bucket identity, and each backed-up object's
checksum; it does not restore data, prove that the backup can be successfully applied, or verify
external/off-host copies. A failed backup may leave an incomplete timestamp directory; do not treat
it as valid unless `verify` succeeds. Preserve previous verified backups until a newer one is
verified.

### Restore only into disposable local data

Restore is destructive: PostgreSQL objects in the configured database may be dropped/replaced and
**all current objects** in the configured MinIO bucket are removed before the archived objects are
copied back. The tool refuses environments other than local/development/test and requires an exact
confirmation phrase, but those safeguards do not protect the wrong local database or bucket.

Before restoring, confirm the repository, `.env`, Compose project, database and MinIO bucket are the
intended disposable local targets; stop application/worker writes through the approved local
procedure; and create and successfully verify a fresh backup of the current state. Verify the source
backup again. Restore has no preview/dry-run mode and does not provide an automatic rollback if the
restore partially fails. Do not use it on shared, staging, or production data. For any doubt, stop
and ask the data owner rather than running the command.

```powershell
uv run python scripts/local_data.py restore --backup .local/backups/<timestamp> --confirm "RESTORE LOCAL DATA"
```

After an approved local restore, inspect the command result and service health, then verify the
expected local records and objects using the application's read-only views. Do not claim disaster
recovery readiness until isolated restore drills, off-host encrypted copies, retention policy and
measured RPO/RTO are established.
