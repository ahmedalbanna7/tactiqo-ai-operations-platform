## Objective

Describe the user/business outcome and reference the Master Plan task IDs.

## Changes

- [ ] Domain/application contracts
- [ ] Infrastructure adapters
- [ ] API/UI
- [ ] Database migration
- [ ] Documentation/runbook/ADR

## Security and authorization

- [ ] Tenant, actor, department, team, project, classification, and policy scope remain server-derived.
- [ ] Authorization happens before resource lookup and prevents existence leakage.
- [ ] Secrets and sensitive payloads are absent from source, logs, events, queues, prompts, and responses.
- [ ] External input and tool/RAG results are treated as untrusted data.
- [ ] Mutations are idempotent and approval-gated where required.
- [ ] Negative and isolation tests cover the changed boundary.

## Data and migrations

- [ ] No schema change, or a forward migration is included.
- [ ] Backward compatibility and rollout order are documented.
- [ ] Rollback/forward-recovery and data-retention impact are documented.

## Verification

- [ ] Ruff format and lint
- [ ] Mypy strict
- [ ] Pytest
- [ ] ESLint and TypeScript
- [ ] Frontend production build
- [ ] Compose validation and relevant smoke tests
- [ ] Dependency, secret, license, and SBOM checks

Evidence and commands:

```text
Paste sanitized evidence here. Never paste credentials or customer data.
```

## Architecture decision

- [ ] No material architecture boundary changed.
- [ ] A new or updated ADR is included under `docs/adr/`.

## Operational handoff

Known limitations:

Rollback or forward-recovery path:

Next Master Plan task IDs:
