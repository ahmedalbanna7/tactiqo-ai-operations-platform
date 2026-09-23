# Tactiqo execution roadmap

## Goal

Deliver the target architecture in additive, independently testable increments.
No phase may bypass tenant isolation, authorization, audit, or the engineering
constitution. Each new provider, agent, tool, parser, or output format is an
adapter/capability registration rather than a modification to existing domain
logic.

## Engineering rules

1. Define domain models and application ports before infrastructure adapters.
2. Keep one responsibility per service and prefer composition over inheritance.
3. Depend on abstractions; provider SDKs never enter agent or business modules.
4. Extend registries with new implementations; do not add provider conditionals
   across orchestration (`Open/Closed Principle`).
5. Keep ports narrow so every adapter is substitutable and testable (`Interface
   Segregation` and `Liskov Substitution`).
6. Derive tenant/user scope on the server and apply it before persistence,
   retrieval, tool discovery, execution, and output.
7. Use free-tier APIs initially, but treat quotas, privacy, and availability as
   runtime capabilities. No free provider is a permanent architectural default.
8. Keep secrets in environment/secret management; never source, logs, queues,
   plans, prompts, API responses, or browser storage.

## Phase 0 — current operational foundation

Status: substantially implemented locally.

- chat-first Next.js UI and FastAPI API;
- LangGraph orchestration and PostgreSQL checkpoints;
- PostgreSQL, Redis, RabbitMQ, MinIO;
- MCP client gateway, policy, approval and audit boundaries;
- tenant-scoped Jira/Slack connection persistence;
- encrypted OAuth credentials, PKCE, refresh, disable and verification;
- background ingestion worker foundation;
- Onyx removed; RAG deferred behind ports.

Exit gate: existing automated quality gates stay green and no credential appears
in API output, logs, database plaintext, or git.

## Phase 1 — identity and organization control plane

Deliver:

- production Identity Provider port and JWT/session adapter;
- organizations and organization memberships;
- Owner, Admin, Integration Manager, Department Manager, Team Manager, Project
  Manager, Employee, Auditor/Risk Reviewer roles;
- departments, optional teams, projects, managers and dated memberships;
- server-derived enriched `ExecutionContext`;
- RBAC + ABAC + ReBAC Policy Compiler with versioned decisions;
- PostgreSQL constraints and row-level-security defense in depth;
- Company Settings UI for people, roles, departments, teams and managers;
- `Preview as User` policy simulation without impersonating or exposing content.

Exit gate:

- automated cross-tenant and cross-department negative tests;
- revoked membership denies the next request;
- organization-scoped administration requires Owner/Admin authority;
- no client can forge tenant, department, team, project, role, or clearance.

## Phase 2 — Agent Catalog and access assignments

Deliver:

- category, agent definition, version and capability models;
- organization-installed agent packs;
- department/team/project/role/user assignments;
- separate visible, usable, draft, execute, publish and administer grants;
- data domain, classification, MCP tool, approval, quota and cost policies;
- agent-first settings screen and reverse department/team assignment view;
- employee agent list returned by the server from effective entitlements only;
- generic Department Operations Agent for future departments.

Initial catalog:

- Planner, Executive, PMO, Construction, Events, Risk, Product/Development,
  Automation, Finance, IT, HR, Procurement, Legal, Sales, Marketing, Support,
  Operations/Facilities, Quality/HSE, Knowledge and Communications;
- Email, Reports, Power BI, Data Operations, Documents, Spreadsheets,
  Presentations, Images, Video, Meetings/Calendar and Social/Campaign execution;
- F4.1 Review, Safety & Recovery as an independent control-plane capability.

Exit gate: a user cannot discover, invoke, retrieve data for, or receive output
from an unassigned agent, including through direct API calls or prompt attempts.

## Phase 3 — Planner and adaptive execution classifier

Deliver:

- deterministic Fast/Standard/Background classifier;
- typed, versioned task-plan schema;
- Planner Agent restricted to planning and read-free metadata estimates;
- step dependencies, agent/data-reader/tool assignment, scope, risk, budget,
  approval and completion evidence;
- micro-plan fast path for simple chat/read requests;
- policy compilation for every step;
- safe foreground-to-background escalation at checkpoints;
- plan view and approval checkpoints in chat.

Exit gate:

- simple requests do not call a separate planning model;
- unauthorized plan steps execute zero reads/calls;
- material plan changes trigger authorization again;
- performance budgets demonstrate that the fast path stays responsive.

## Phase 4 — durable Worker Agent Runtime

Deliver:

- workload/risk-specific RabbitMQ queues;
- signed immutable work envelopes containing references and minimum scope;
- job, attempt, checkpoint, progress, artifact and cancellation persistence;
- leases, heartbeat, idempotency, concurrency limits, retry/backoff and DLQ;
- document/OCR, media, report/BI and integration/automation worker profiles;
- current-policy revalidation at safe checkpoints;
- background-jobs UI with stages, cancel, retry, approval and artifacts.

Exit gate:

- worker restart resumes without duplicated side effects;
- cancellation and membership/connection revocation stop at a safe checkpoint;
- queues contain no large file, raw token, or unrestricted identity object;
- poison work reaches DLQ with sanitized diagnostic evidence.

## Phase 5 — LLM Bank (free-first)

Deliver:

- `LanguageModelPort`, request/result contracts and capability descriptor;
- provider registry and policy-aware router;
- initial approved free-tier API and/or local-model adapters;
- deterministic test adapter retained for repeatable tests;
- health, circuit breaker, rate-limit handling, retry and bounded fallback;
- Arabic/English, structured-output, tool-calling and context capabilities;
- per-tenant provider allowlist, residency, classification, quota and budget;
- encrypted secret references and sanitized usage accounting;
- adapter conformance and routing tests.

Future addition path:

```text
implement LanguageModelPort
-> declare capabilities and policy attributes
-> register adapter
-> configure secret and tenant allowlist
-> run conformance/evaluation suite
-> activate routing policy
```

OpenAI or any paid provider follows this path. No free adapter or agent code is
edited or removed.

Exit gate: provider outage/rate limit fails over only to an approved equivalent;
sensitive data never leaves its permitted residency/classification boundary.

## Phase 6 — Embedding Bank and versioned vector spaces

Deliver:

- `EmbeddingPort`, registry, router and descriptor;
- initial Arabic/English free-tier and/or local embedding adapter;
- batch limits, health, rate limiting, privacy and residency policy;
- embedding-space id including provider/model/version/dimensions/normalization;
- parallel indexes and background re-index migration;
- paid-provider adapters, including a future OpenAI adapter, without rewriting
  ingestion or retrieval;
- multilingual retrieval evaluation and adapter conformance tests.

Exit gate: vectors from different embedding spaces are never compared; active
space changes only after retrieval-quality and tenant-isolation gates pass.

## Phase 7 — ACL-aware ingestion and RAG

Deliver:

- PDF, Word, Excel, CSV, PowerPoint, image/OCR, audio/video transcription parsers;
- source normalization, content hashes, versions and lineage;
- organization/department/team/project/user ACL and classification on every chunk;
- PostgreSQL full-text + pgvector hybrid retrieval and RRF/reranking;
- mandatory authorization predicates before retrieval;
- source ACL refresh/revocation handling;
- document prompt-injection detection and untrusted-content envelopes;
- citations and source preview down to page, sheet/cell, timestamp, message or issue;
- Arabic/English retrieval-quality, permission and injection evaluation datasets.

Exit gate: zero unauthorized chunks enter model context, citations resolve only
for authorized users, and ACL revocation removes access predictably.

## Phase 8 — scoped MCP tools and execution agents

Deliver:

- owner assignment of Integration Managers;
- department/team/project/agent/tool scope on every connection;
- Jira and Slack production OAuth validation;
- email and calendar MCP/adapters;
- report/document/spreadsheet/presentation/image/video/Power BI adapters;
- automation design, dry-run, activation, monitoring and rollback;
- draft versus execute/publish controls and configurable approval chains;
- post-tool output filtering, prompt-injection scan and artifact lineage.

Exit gate: provider ACL and Tactiqo internal scope are both enforced; every
external side effect is idempotent, approved when required, verified and audited.

## Phase 9 — F4.1 assurance and production hardening

Deliver:

- independent plan, retrieval, tool, output and artifact review;
- fallback/recovery policy and safe partial-result behavior;
- adversarial prompt/tool/document testing;
- policy, citation and output validation;
- observability without sensitive data;
- SLOs, capacity tests, backup/restore, key rotation and disaster recovery;
- audit export, retention, legal hold and incident response;
- security review and production deployment runbooks.

Exit gate: red-team, isolation, recovery, load, security and governance suites
pass against the release candidate.

## Cross-phase UI delivery

The UI evolves incrementally while preserving the simple chat experience:

1. Company Settings navigation appears only from server entitlements.
2. People, departments, teams and managers become functional in Phase 1.
3. Agent categories, assignments and effective-access preview arrive in Phase 2.
4. Plans, assigned agents/readers and approvals arrive in Phase 3.
5. Background progress, cancel/retry and artifacts arrive in Phase 4.
6. Provider policies and usage become visible to owners without exposing keys.
7. RAG citations/source preview and source ACL management arrive in Phase 7.
8. Tool managers, scoped connections and action approvals arrive in Phase 8.

## Definition of done for every increment

- domain/application/infrastructure boundaries remain intact;
- public API and migration are versioned and documented;
- positive, negative, isolation and failure tests pass;
- type, lint, unit, integration and relevant end-to-end checks pass;
- secrets and sensitive payloads are absent from logs and source control;
- authorization happens before resource lookup to prevent existence leakage;
- monitoring, rollback and failure behavior are defined;
- architecture and operational documentation reflect the deployed behavior.

