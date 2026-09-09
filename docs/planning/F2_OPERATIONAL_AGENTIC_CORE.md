# F2 Operational Agentic Core Implementation Plan

Status: approved for implementation on 2026-09-09.

## Goal

Deliver a real, governed operational flow in which one LangGraph supervisor
combines authorized Jira, Slack, and project-document evidence, delegates work
to specialist agents, produces a cited answer, and executes one user-approved
action safely.

## Delivery order

### F2.0 — Baseline and contracts

- Re-run F1 quality and Docker gates from a clean checkout.
- Freeze Jira, Slack, retrieval, citation, agent-state, and approval contracts.
- Add connector capability/risk metadata and correlation/idempotency fields.
- Add minimum authenticated actor and configured source-scope mapping required
  for real connector data; local development identity remains demo-only.

### F2.1 — Real RAG path

- Run the approved Onyx knowledge profile and authenticated adapter.
- Preserve PostgreSQL canonical documents/elements and MinIO originals.
- Evaluate Arabic/English chunking and embedding profiles before selection.
- Enforce ACL filters before retrieval and revalidate every returned citation.
- Add source preview, freshness, conflict, and degraded-index states.
- Add prompt-injection and data-leakage retrieval evaluation cases.

### F2.2 — LangGraph supervisor and specialist subgraphs

- Implement typed `OperationalSupervisor` state and deterministic routing
  envelope.
- Add Knowledge, Jira, Slack, Project Management, Risk, Reporting, and initial
  Review specialist subgraphs.
- Apply per-run budgets for steps, tools, tokens, latency, and concurrency.
- Preserve checkpoints, cancellation, ordered events, retry classification, and
  explicit safe failure.
- Permit parallel read branches only within configured limits; serialize
  mutations and approvals.

### F2.3 — Jira MCP

- Implement an independently deployable typed Jira MCP server.
- Store OAuth/API credentials outside Git and logs.
- Support scoped project/issue/sprint/search reads first.
- Add create/update/comment actions only behind preview, policy, approval,
  idempotency, and post-action verification.
- Handle pagination, rate limits, cursors, retries, revocation, and audit.

### F2.4 — Slack MCP

- Implement an independently deployable typed Slack MCP server.
- Enforce channel allowlists and source-level access.
- Support channel/thread/search reads with provenance and timestamps.
- Add message/reminder actions only behind preview, policy, approval,
  idempotency, and post-action verification.
- Handle pagination, rate limits, cursors, retries, revocation, and audit.

### F2.5 — Cross-source operational flow

- Link Jira work items, Slack discussions/decisions, and document evidence.
- Produce cited project status, blockers, conflicting signals, and risk
  candidates.
- Show source freshness and uncertainty in the chat response.
- Allow one reviewed Jira or Slack action after explicit approval.
- Record the complete supervisor/subgraph/tool/approval trace.

## Agent authority

- Agents may observe, retrieve, classify, summarize, compare, recommend, and
  draft inside the authorized scope.
- Agents cannot grant access, change policy, approve their own work, accept a
  risk, publish an official decision, or execute a material action autonomously.
- Deterministic authorization, schema validation, tool-risk classification, and
  approval engines are authoritative.
- Retrieved documents, Jira content, Slack messages, and MCP results are
  untrusted inputs and never become system instructions.

## Definition of done

F2 is complete only when an authenticated test user can select an authorized
project, ask for its status, receive a grounded answer using Jira, Slack, and
document evidence with working citations and freshness, then approve or reject
one proposed action. Unauthorized sources remain inaccessible, rejected actions
produce no side effect, approved actions execute once, and the full run is
auditable and resumable.

All unit, contract, integration, security-isolation, retrieval-evaluation,
frontend, migration, and Docker gates must pass. Real connector tests use
sandbox workspaces only.

## Required configuration before live integration

- Jira Cloud site and sandbox project.
- Jira OAuth application or approved scoped service account.
- Slack sandbox workspace and approved Slack application.
- Allowed Jira projects and Slack channels.
- Onyx deployment profile and service credential.
- Initial Arabic/English retrieval evaluation documents and questions.
