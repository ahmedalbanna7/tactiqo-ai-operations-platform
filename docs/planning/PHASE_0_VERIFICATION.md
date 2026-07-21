# Phase 0 Foundation Verification

Verification date: 2026-07-21

## Implemented

- Typed FastAPI process composition and settings.
- Liveness and fail-closed readiness for PostgreSQL, Redis, RabbitMQ, and MinIO.
- Correlation-ID validation and propagation.
- Strict TypeScript Next.js shell.
- Local core Compose model with persistent data volumes and health checks.
- Provider-neutral `KnowledgeSearchPort` and `DocumentParser` contracts.
- Pinned official GitHub upstream manifest and guarded checkout script.
- Backend/frontend/Compose CI definitions.
- Local setup and upstream integration runbooks.

## Exact checks

| Check | Result |
|---|---|
| Python 3.12 syntax compilation | Passed |
| Python 3.12 tests | 8 passed, warnings treated as errors |
| Ruff lint and format | Passed; 27 files |
| mypy strict type checking | Passed; 21 source files |
| pnpm frozen installation | Passed from committed `pnpm-lock.yaml` |
| Frontend ESLint and TypeScript | Passed |
| Next.js production build | Passed; `/` and `/_not-found` prerendered |
| Required class/function/method docstrings | Passed |
| Docker Compose model validation | Passed |
| Locked Docker image builds | Passed for API and Web |
| Compose runtime health | Passed; all 6 services healthy |
| First-request API readiness | Passed; HTTP 200 with 4 healthy components |
| Persistent-volume restart test | Passed for PostgreSQL, Redis, RabbitMQ, and MinIO volume |
| Browser UI smoke test | Passed; HTTP 200, visible shell, no console errors/warnings |
| Upstream lock JSON parsing | Passed |
| Upstream PowerShell script parsing | Passed |
| Pinned upstream source verification | Passed; 4 origins, commits, required files, and clean worktrees |
| `uv.lock` installation | Passed on host and in the API image |

The runtime, local quality environment, Docker image, and CI are all configured
for Python 3.12. Frontend checks use Node.js 22 and pnpm 10.33.0.

## Downloaded upstream source

| Component | Release | Exact commit | Checkout |
|---|---:|---|---|
| Onyx | `v4.3.9` | `1da679cefc96165c6b9b64c3bc769584b88f88c2` | Full release worktree |
| Unstructured | `0.24.1` | `cda16b3f2170019be9c6ea5635946fb3eaa2d66f` | Sparse code worktree; binary fixtures excluded |
| LangGraph | `1.2.9` | `95af6a00718588e7b7ce17310e8006d267896a77` | Full release worktree |
| LangChain Core | `1.4.9` | `1c3a4186cf2ba4f28face59118ac7786de009f91` | Full release worktree |

All worktrees use official GitHub origins, are detached at the manifest commit,
and are ignored by the Tactiqo product repository. The Unstructured sparse
checkout includes its package source and root build metadata while excluding
large example and test fixtures that are not runtime dependencies.

## Runtime verification details

- PostgreSQL, Redis, RabbitMQ, MinIO, API, and Web were built and started with
  Docker Compose. Every service health check passed.
- Published ports bind to `127.0.0.1` and use isolated defaults so the stack does
  not interfere with other local projects.
- The first readiness request after a fresh API container start returned HTTP
  200. Per-component timeouts preserve completed dependency results.
- Temporary PostgreSQL, Redis, RabbitMQ, and MinIO-volume markers survived
  service restarts. All verification markers were removed afterward without
  deleting the persistent volumes.
- API dependencies are installed from `uv.lock`; frontend dependencies are
  installed from `pnpm-lock.yaml`; base and infrastructure images are pinned by
  tag and digest.
- The in-app browser loaded the Phase 0 shell at `http://127.0.0.1:13000` with a
  visible heading and status region and no browser console errors or warnings.

Phase 0 is verified and ready to serve as the baseline for Phase 1. This does
not approve or activate capabilities assigned to later architecture gates.

## Upstream activation state

Downloading source does not activate a subsystem:

- Onyx and Unstructured remain disabled until the Phase 3 RAG/ACL architecture
  and adapter contracts are approved.
- LangGraph and LangChain remain disabled until the Phase 4 graph, state,
  checkpoint, memory, tool, guardrail, and evaluation design is approved.
- RabbitMQ is present for local infrastructure health only. No queue/exchange or
  worker framework is selected before its topology decision.
