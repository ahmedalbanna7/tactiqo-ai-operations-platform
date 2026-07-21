# Repository Structure

Status: proposed complete monorepo hierarchy. Directories are scaffolded now;
implementation files are added incrementally by approved phase. A directory's
presence does not mean its subsystem is active or deployed.

```text
Tactiqo/
|-- AGENTS.md
|-- README.md
|-- .editorconfig
|-- .env.example                 # Phase 0; placeholders only
|-- .gitignore
|-- .python-version              # Phase 0 after runtime verification
|-- Makefile                     # portable developer commands
|-- pyproject.toml               # pinned Python workspace/tooling
|-- package.json                 # JS workspace commands
|-- pnpm-lock.yaml               # committed generated lockfile
|-- pnpm-workspace.yaml
|-- docker-compose.yml           # core plus opt-in profiles
|
|-- .github/
|   |-- CODEOWNERS
|   |-- dependabot.yml
|   |-- pull_request_template.md
|   `-- workflows/
|       |-- backend-ci.yml
|       |-- frontend-ci.yml
|       |-- migrations.yml
|       |-- security.yml
|       `-- architecture.yml
|
|-- apps/
|   |-- api/                     # FastAPI composition and process entrypoint
|   |   |-- Dockerfile
|   |   `-- src/tactiqo_api/
|   |       |-- main.py
|   |       |-- composition.py
|   |       `-- lifecycle.py
|   |-- worker/                  # normal RabbitMQ command/job worker entrypoint
|   |   |-- Dockerfile
|   |   `-- src/tactiqo_worker/
|   |       |-- main.py
|   |       `-- composition.py
|   |-- parser-worker/           # isolated document/OCR compute boundary
|   |   |-- Dockerfile
|   |   `-- src/tactiqo_parser_worker/
|   |       |-- main.py
|   |       `-- composition.py
|   `-- web/                     # Next.js App Router application
|       |-- Dockerfile
|       |-- app/
|       |-- components/
|       |-- features/
|       |-- lib/
|       |-- public/
|       `-- tests/
|
|-- backend/
|   |-- alembic.ini
|   |-- migrations/
|   |   |-- env.py
|   |   |-- script.py.mako
|   |   `-- versions/
|   |-- src/tactiqo/
|   |   |-- shared/
|   |   |   |-- domain/          # common value objects; never a dumping ground
|   |   |   |-- application/     # shared contracts and UoW abstractions
|   |   |   |-- infrastructure/  # config, DB, cache, queues, telemetry
|   |   |   `-- presentation/    # error and transport conventions
|   |   |
|   |   |-- identity/
|   |   |-- organization/
|   |   |-- company_setup/
|   |   |-- industries/
|   |   |-- projects/
|   |   |-- operations/
|   |   |-- delivery/
|   |   |-- quality/
|   |   |-- risks/
|   |   |-- connectors/
|   |   |-- ingestion/
|   |   |-- knowledge/
|   |   |-- search/
|   |   |-- chat/
|   |   |-- agents/
|   |   |-- approvals/
|   |   |-- reports/
|   |   |-- notifications/
|   |   |-- audit/
|   |   `-- evaluation/
|   |
|   `-- tests/
|       |-- unit/
|       |-- integration/
|       |-- api/
|       |-- architecture/
|       |-- security/
|       |-- contracts/
|       |-- migrations/
|       |-- performance/
|       `-- fixtures/
|
|-- packages/
|   |-- api-client/              # generated from versioned FastAPI OpenAPI
|   |-- contracts/               # generated JSON Schema/TS artifacts
|   |-- ui/                      # accessible shared React components
|   |-- eslint-config/
|   |-- typescript-config/
|   `-- tailwind-config/
|
|-- industry-packs/
|   |-- schemas/                 # versioned pack validation schemas
|   |-- general-pmo/
|   |-- construction/            # populated only if selected for pilot
|   |-- events/                  # populated only if selected for pilot
|   |-- consulting/
|   `-- software-delivery/       # optional pack, never horizontal-core logic
|
|-- infra/
|   |-- docker/
|   |   |-- api/
|   |   |-- web/
|   |   |-- worker/
|   |   |-- parser-worker/
|   |   `-- observability/
|   |-- compose/
|   |   |-- core.yml
|   |   |-- knowledge.yml
|   |   `-- observability.yml
|   |-- onyx/                    # pinned config/integration notes; no core fork
|   |-- rabbitmq/
|   |-- postgres/
|   |-- otel/
|   |-- terraform/               # added when AWS/Azure target is approved
|   |   |-- modules/
|   |   `-- environments/
|   `-- k8s/                     # added when first deployment requires it
|       |-- helm/
|       `-- environments/
|
|-- docs/
|   |-- product/
|   |   |-- CODEX_ENGINEERING_CONSTITUTION.md
|   |   `-- AI_OPERATIONS_PLATFORM_MASTER_SPEC.md
|   |-- architecture/
|   |   |-- SYSTEM_HIERARCHY.md
|   |   |-- REPOSITORY_STRUCTURE.md
|   |   |-- context-diagrams/
|   |   |-- data-flows/
|   |   `-- module-boundaries/
|   |-- adr/
|   |-- planning/
|   |-- decisions/
|   |-- api/
|   |-- events/
|   |-- jobs/
|   |-- security/
|   |-- rag/
|   |-- agents/
|   |-- runbooks/
|   |-- deployment/
|   |-- migrations/
|   |-- testing/
|   `-- capacity/
|
|-- scripts/
|   |-- dev/
|   |-- ci/
|   |-- db/
|   |-- data/
|   |-- evaluation/
|   `-- release/
|
|-- evals/
|   |-- datasets/
|   |-- retrieval/
|   |-- answers/
|   |-- agents/
|   `-- reports/
|
`-- tests/
    |-- e2e/
    |-- load/
    |-- security/
    `-- smoke/
```

## Standard backend module template

Each business module starts small and adds only folders it needs:

```text
module_name/
|-- domain/
|   |-- entities.py
|   |-- value_objects.py
|   |-- policies.py
|   |-- events.py
|   `-- errors.py
|-- application/
|   |-- commands/
|   |-- queries/
|   |-- services.py
|   |-- dto.py
|   `-- ports.py
|-- infrastructure/
|   |-- persistence/
|   |-- adapters/
|   `-- mappings.py
|-- presentation/
|   |-- api/
|   |-- jobs/
|   `-- schemas.py
`-- public.py
```

`public.py` is the supported synchronous cross-module surface. Versioned domain
events are the asynchronous surface. Other modules must not import internal
repositories, ORM mappings, or private implementation files.

## Structure rules

- `apps/` contains process composition, not business rules.
- `backend/src/tactiqo/` contains the Python product modules.
- `packages/` contains generated contracts and reusable frontend/tooling code.
- `industry-packs/` contains versioned data/configuration, not authorization
  rules or vendor code.
- `infra/` contains deployment wiring. Business code cannot import it.
- `docs/product/` preserves the governing inputs.
- `evals/` contains permission-safe, versioned AI/RAG regression datasets.
- Root `tests/` covers cross-process behavior; module/unit tests stay under
  `backend/tests/` or `apps/web/tests/`.
- Empty future directories are not permission to deploy unused components.
