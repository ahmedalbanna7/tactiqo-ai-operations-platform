# ADR-0001: Function-first Agentic Knowledge Core

- Status: Approved
- Date: 2026-07-22
- Decision owner: Product owner

## Context

The original roadmap placed identity, organization hierarchy, connectors,
knowledge retrieval, and agent orchestration in sequential phases. The product
owner explicitly reprioritized the first usable increment toward the functional
system experience: conversational chat, bounded agent orchestration, MCP tools,
RAG, citations, and human-approved actions.

This changes delivery order, not the engineering constitution. Security,
privacy, auditability, evidence, approval, and provider boundaries remain
mandatory.

## Decision

Build an F1 Agentic Knowledge Core before the complete Phase 1 identity and
organization user experience.

The increment will:

- use a local development execution context through `AuthorizationPort`;
- carry actor, organization, project, classification, and policy-version fields
  through conversations, documents, runs, tool calls, and citations;
- route model access through `ModelProviderPort`;
- use LangGraph as the single workflow runtime;
- expose MCP servers only through a policy-enforcing `ToolGateway`;
- place Onyx behind `KnowledgeSearchPort` and Unstructured behind
  `DocumentParser`;
- require explicit approval for mutating tools;
- store conversations, runs, approvals, and audit events in PostgreSQL;
- retain MinIO as the original-file store and RabbitMQ for ingestion work.

OpenAI's Responses API is the first model adapter. A deterministic local adapter
keeps tests and the local demonstration runnable without an API key.

## Consequences

- F1 proves the product's primary interaction before all enterprise identity
  screens exist.
- Local development is intentionally single-organization and uses a clearly
  marked development principal.
- Production or shared deployment remains blocked until real authentication,
  server-derived authorization, RLS, and security-isolation tests are complete.
- Later identity and industry modules plug into stable ports and execution
  context rather than rewriting chat, tools, or RAG.
- Backward-compatible migrations and composition changes may still be required;
  the decision promises extension without a core rewrite, not zero future edits.

## Rejected alternatives

- Building every specialist agent before a working retrieval/tool loop: this
  creates prompt aliases without reliable data, tools, or evaluations.
- Letting the model provider execute remote MCP tools directly by default: this
  bypasses the platform's central policy, approval, and audit gateway.
- Adding a second vector index beside Onyx/Vespa: this violates the approved
  knowledge boundary without an evaluated use case.
