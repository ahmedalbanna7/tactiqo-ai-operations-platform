# ADR-0002: LangGraph Operational Agentic Core

- Status: Approved
- Date: 2026-09-09
- Decision owner: Product owner

## Context

F1 proved the local chat, durable run, MCP, approval, ingestion, and retrieval
boundaries. The product owner has prioritized real operational value before the
remaining administration surfaces: activate the production-oriented RAG path,
connect Jira and Slack through governed MCP adapters, and place specialist
agents beneath a single coordinating agent.

This is a delivery-order decision. It does not waive identity, source ACL,
classification, audit, or human-approval requirements.

## Decision

LangGraph is the platform's only agent-workflow runtime. F2 will implement one
typed `OperationalSupervisor` graph that delegates bounded work to specialist
subgraphs:

- `KnowledgeAgent` for authorized RAG and citations;
- `JiraAgent` for Jira discovery, analysis, and approval-gated actions;
- `SlackAgent` for channel/thread retrieval and approval-gated messages;
- `ProjectManagementAgent` for delivery-state synthesis;
- `RiskAgent` for evidence-backed risk candidates;
- `ReportingAgent` for cited operational summaries;
- an initial `ReviewAgent` slice from F4.1 for groundedness and safe output.

Agents do not call vendor APIs directly. Jira and Slack are exposed through
typed MCP servers behind the existing `ToolGateway`, deterministic policy,
schema validation, timeouts, audit, and human approval. PostgreSQL remains the
canonical platform store; connected systems remain authoritative for their
source records. Onyx remains behind `KnowledgeSearchPort`.

The first acceptance flow is a cited project-status request combining Jira,
Slack, and project documents, followed by one explicitly approved Jira or Slack
action.

## Consequences

- Specialist agents can be added as subgraphs without replacing the chat or
  tool infrastructure.
- Cross-source execution has one trace, budget, cancellation path, checkpoint,
  and approval lifecycle.
- Minimum production identity and source-scope mapping must be implemented in
  the same increment before real company data is retrieved.
- Jira is the first work-management connector and Slack the first communication
  connector.
- Direct SDK calls from agent nodes, autonomous write actions, duplicate agent
  runtimes, and hidden provider fallback are prohibited.

## Validation

- Typed-state and routing unit tests.
- Mocked Jira/Slack MCP contract tests.
- Sandbox integration tests for read, approval, rejection, idempotency, retry,
  revocation, and rate limits.
- Arabic/English RAG evaluation with citation, ACL, injection, conflict, and
  freshness cases.
- End-to-end cross-source scenario with a durable LangGraph checkpoint.

## Revisit triggers

Revisit only if measured scale, isolation, or reliability evidence requires a
separate deployable workflow service. A new ADR is required before introducing
another orchestration runtime.
