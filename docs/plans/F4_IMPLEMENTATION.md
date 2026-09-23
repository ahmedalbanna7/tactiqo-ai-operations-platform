# F4 — Planner, Supervisor, and adaptive LangGraph orchestration

Status: implemented and verified locally on 2026-09-14. Durable execution of Background
jobs remains the explicitly separate F5 worker handoff.

## Delivered

- Deterministic Fast, Standard, and Background workload classification before LLM use.
- Content-free workload estimates for input, files, media, records, tools, steps, risk,
  and approvals.
- Configurable foreground limits and safe Background escalation before side effects.
- Strict Pydantic execution plan schema with forbidden extra fields.
- Versioned plans, dependency validation, deliverables, evidence requirements, budgets,
  action levels, modes, risks, approvals, and deterministic step idempotency keys.
- Least-privilege agent and data-reader selection for Chat, Knowledge, Data, and Planner.
- Exact declared RAG collections, MCP connections, and tool names per planned step.
- Policy-version compilation before retrieval, tool execution, review, and resume.
- PostgreSQL-backed LangGraph checkpoints and durable run/audit events.
- Explicit Supervisor nodes for authenticate, guardrails, memory, classify, authorize,
  route, retrieve, plan, execute, verify, review, respond, cancel, and safe recovery.
- Hard elapsed-time and tool-call ceilings, resumable approvals, cancellation, and
  deterministic terminal states.
- Dependency-wave scheduling: independent steps may run together, while shared MCP/tool
  resources are serialized deterministically.
- Background-class work returns a safe deferred status without foreground side effects;
  durable job execution belongs to F5 Worker Runtime.

## Runtime flow

```text
authenticate -> guardrails -> memory -> classify -> authorize -> route
  Fast       -> review -> respond
  Knowledge  -> retrieve -> review -> respond
  Standard   -> plan -> execute? -> verify -> review -> respond
  Background -> strict plan -> safe defer -> review -> respond -> F5 handoff
```

All audit payloads exclude message and source contents. Every classified run records the
route, reason, estimate, selected agent, policy version, and plan identifier.

## Boundary with F4.1 and F5

F4 performs deterministic structural review and fail-closed authorization. Independent
adversarial output/artifact review remains F4.1. Durable execution of deferred large jobs,
fan-out, and worker leases remains F5; F4 never simulates their completion.
