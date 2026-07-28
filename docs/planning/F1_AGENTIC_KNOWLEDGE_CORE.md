# F1 Agentic Knowledge Core Implementation Plan

Status: approved for implementation on 2026-07-22.

## Scope and assumptions

F1 delivers one end-to-end local flow:

1. Create a conversation and stream an agent response.
2. Upload a supported document, parse it asynchronously, and preserve source
   provenance.
3. Retrieve evidence through `KnowledgeSearchPort` and render citations.
4. Discover and call tools from an MCP server.
5. Pause mutating tool calls for explicit approve/reject decisions.
6. Persist conversations, runs, events, approvals, and audit records.

The full identity, organization editor, Industry Pack UI, and external SaaS
connectors are not activated in F1. Their required context fields and ports are
present from the first schema.

## Architecture and affected modules

- `chat`: conversations, messages, streaming, and run history.
- `agents`: typed LangGraph state, bounded orchestration, and model-provider
  ports.
- `tools`: MCP registry/gateway, policies, approvals, and tool audit.
- `knowledge`: documents, canonical elements, citations, and search contracts.
- `ingestion`: RabbitMQ jobs and isolated Unstructured parsing.
- `integrations/onyx`: authenticated ingestion/search adapter only.
- `shared`: execution context, database lifecycle, and composition.
- `apps/api`: HTTP/SSE transport only.
- `apps/worker`: document parsing worker.
- `apps/mcp_demo`: safe local MCP proof server.
- `apps/web`: chat-first user experience.

## Data and migration impact

The first F1 migration introduces:

- conversations and messages;
- agent runs and ordered run events;
- approval requests and tool audit events;
- knowledge documents and canonical document elements.

All controlled rows carry organization, actor, project, classification, and
policy-version context where applicable. PostgreSQL is authoritative. Onyx is a
derived index and MinIO owns original file bytes.

## API, event, and job contracts

- `POST/GET /api/v1/conversations`
- `GET /api/v1/conversations/{id}/messages`
- `POST /api/v1/conversations/{id}/messages`
- `GET /api/v1/runs/{id}`
- `GET /api/v1/runs/{id}/events`
- `POST /api/v1/runs/{id}/cancel`
- `POST /api/v1/approvals/{id}/decision`
- `POST/GET /api/v1/knowledge/documents`
- RabbitMQ `knowledge.parse.v1` jobs with bounded retry and DLQ.

SSE events are ordered and resumable by event sequence. Mutation contracts
include correlation ID, actor scope, and idempotency identifiers.

## Security, guardrails, and approval

- Input length and prompt-injection signals are checked before orchestration.
- Tool inputs are validated against discovered JSON Schema.
- Read-only tools may run automatically under policy.
- Mutating or destructive tools always pause for a human decision.
- Tool output is untrusted content, size-bounded, redacted, and never promoted
  to system instructions.
- Retrieval is fail-closed when a citation cannot be mapped to an authorized
  platform document.
- Secrets are `SecretStr` configuration and never included in API output or
  traces.
- Production startup rejects the local development authorization adapter.

## Capacity, failure, and fallback

- Agent iterations, tool calls, output size, execution time, and concurrent runs
  are bounded.
- Database events preserve the user-visible run timeline.
- LangGraph checkpoints allow interrupted approval flows to resume.
- Parser work uses RabbitMQ prefetch, bounded retries, and a dead-letter queue.
- The deterministic model and local lexical search adapters are development and
  test fallbacks, not hidden production fallbacks.
- Provider, MCP, Onyx, or parser failure produces an explicit degraded result;
  it never fabricates evidence or reports an action as completed.

## User experience

The interface follows familiar conversational patterns: conversation sidebar,
centered message stream, multiline composer, attachment action, streaming
status, citations, tool activity, and approval cards. It is keyboard accessible,
responsive, and does not expose infrastructure terminology in primary flows.

## Tests and observability

- Unit tests for policies, state transitions, guardrails, and fallback behavior.
- API tests for conversation, streaming, approval, upload, and safe errors.
- Integration smoke tests for PostgreSQL migrations, MCP discovery/calls,
  RabbitMQ processing, MinIO persistence, and optional Onyx health.
- Frontend lint, strict type checking, production build, and browser flow test.
- Structured events for model, retrieval, MCP, approval, and ingestion steps;
  sensitive payload capture remains disabled.

## Definition of done

F1 is complete only when a user can open the web app, create a chat, stream a
response, upload and query a document with a visible citation, call a read-only
MCP tool, approve or reject a mutating MCP tool, and see an honest run timeline.
All applicable quality gates and the six core Docker services must remain
healthy.
