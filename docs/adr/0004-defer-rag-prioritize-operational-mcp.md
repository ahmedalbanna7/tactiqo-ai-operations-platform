# ADR 0004: Defer RAG and prioritize operational MCP integrations

## Status

Accepted by the product owner on 2026-09-10. This decision supersedes the
Onyx-specific runtime choices in ADR 0003; the provider-neutral knowledge ports
and canonical document model remain intact.

## Context

The initial Onyx deployment imposed substantial local operational cost before
the core project-management workflow had been proven. The product owner chose
to validate Jira and Slack connectivity, orchestration, authorization, human
approval, and audit behavior before selecting or building the production RAG
engine.

## Decision

- Remove Onyx containers, volumes, vendored source, credentials, configuration,
  adapter code, and runtime composition.
- Keep `KnowledgeSearchPort`, canonical document storage, parsing boundaries,
  citation models, and content-safety contracts as future extension points.
- Use the current local lexical search only as explicit development behavior;
  no production RAG claim is made.
- Implement Jira and Slack as independent MCP server registrations behind the
  existing tool gateway. Read operations may execute directly; mutations and
  external communications require human approval and audit records.
- Revisit production RAG only after the operational MCP vertical slice passes
  its release gates. A new ADR will select its index, embeddings, retrieval
  profiles, ACL contract, evaluation thresholds, and migration plan.

## Consequences

This reduces local resource use and delivery risk now. Search quality and
document-grounded production answers remain intentionally out of scope until a
later approved increment. Since agents depend on ports rather than a vendor,
the later RAG implementation remains additive.
