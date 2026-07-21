# Tactiqo AI Operations Platform

Tactiqo is a dedicated B2B enterprise platform for project, delivery, quality,
risk, and business-operations intelligence. The product is chat-first,
evidence-grounded, permission-aware, and human-governed.

This repository has completed the Phase 0 executable-foundation baseline. It
contains the local core Compose topology, a FastAPI health/readiness slice, a
strict TypeScript Next.js shell, pinned upstream manifests, and provider-neutral
knowledge/parser ports. No production agent, connector, or retrieval workflow
has been selected or activated yet.

## Governing documents

The project is governed by:

1. `docs/product/CODEX_ENGINEERING_CONSTITUTION.md` -- mandatory engineering law.
2. `docs/product/AI_OPERATIONS_PLATFORM_MASTER_SPEC.md` -- product source of truth.
3. Approved Architecture Decision Records under `docs/adr/`.
4. Approved phase plans and story-level specifications.

Security, privacy, data isolation, and human-approval requirements have the
highest priority.

## Current scope

The first increment establishes:

- Target hierarchy, module boundaries, and the planned monorepo structure.
- FastAPI liveness/readiness with redacted dependency failures.
- A Next.js/strict TypeScript application shell.
- Local PostgreSQL, Redis, RabbitMQ, and MinIO Compose services.
- Pinned official Onyx, Unstructured, LangGraph, and LangChain source references.
- Phase 0/1 plan, acceptance criteria, and explicit approval gates.

See:

- `docs/architecture/SYSTEM_HIERARCHY.md`
- `docs/architecture/REPOSITORY_STRUCTURE.md`
- `docs/planning/PHASE_0_1_FOUNDATION_PLAN.md`
- `docs/decisions/OPEN_DECISIONS.md`
- `docs/runbooks/LOCAL_DEVELOPMENT.md`
- `docs/integrations/UPSTREAM_COMPONENTS.md`

## Status

Phase 0 foundation verified. The six-service local stack is healthy, host and
container builds use committed lockfiles, and quality gates pass. Phase 1 can
begin with identity, organization, authorization, and audit design. RabbitMQ
worker topology, knowledge integration, agents, connectors, and business-domain
implementation remain behind their documented review gates.
