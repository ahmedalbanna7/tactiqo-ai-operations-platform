# Repository Instructions

These instructions apply to the entire repository.

## Mandatory precedence

1. Security, privacy, data isolation, and human-approval requirements.
2. Explicit human decisions and approved ADRs.
3. `docs/product/CODEX_ENGINEERING_CONSTITUTION.md`.
4. `docs/product/AI_OPERATIONS_PLATFORM_MASTER_SPEC.md`.
5. Phase plans, stories, and task notes.

Do not silently resolve conflicts. Explain the conflict, present options and
trade-offs, and obtain approval before recording an exception.

## Required workflow

Before implementing a phase, provide and record:

- Scope and assumptions.
- Repository assessment.
- Architecture and affected modules.
- Data model and migration impact.
- API, event, and job contracts.
- Security and authorization impact.
- Capacity, backpressure, and failure handling.
- Human-approval requirements.
- Tests, observability, and documentation changes.
- Open decisions requiring approval.

Implementation must be incremental, typed, tested, observable, documented, and
reviewable. Preserve unrelated work and report exact verification results.

## Non-negotiable boundaries

- Start as a modular monolith with independent asynchronous workers.
- Keep business rules out of API handlers and infrastructure adapters.
- Domain/application code depends on ports, never vendor SDKs.
- PostgreSQL is the transactional system of record.
- Onyx/Vespa is a derived knowledge index accessed only through
  `KnowledgeSearchPort`.
- Do not introduce a duplicate pgvector knowledge index without approval.
- Unstructured runs in isolated parsing workers behind `DocumentParser`.
- OpenAI is initially accessed only through internal provider interfaces.
- Permissions are server-derived and applied before SQL, search, retrieval,
  model context, citations, exports, notifications, and actions.
- Departments are organization-tree nodes, not workspaces.
- Material configuration, decisions, communications, and actions require the
  configured human approval.
- AI-extracted data remains a candidate until deterministic validation and
  authorized human approval.
- Do not introduce Kafka, a graph database, a new search/vector engine, an
  advanced agent topology, or service extraction without an approved ADR.

## Code expectations

- Python 3.12+, strict typing, useful docstrings, Ruff, and mypy/pyright.
- FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, and PostgreSQL 16+.
- Next.js, React, strict TypeScript, accessible components, and generated API
  contracts.
- Bounded concurrency, idempotency, retries with limits, DLQs, and backpressure.
- Authorization, isolation, migration, failure, and regression tests are part
  of the feature.
- Logs, metrics, traces, runbooks, and rollback notes are part of Definition of
  Done.
