# ADR 0009: Native ACL-aware RAG with PostgreSQL and pgvector

## Status

Accepted for F7 implementation, following the product owner's decision to remove Onyx and build
the platform RAG internally.

## Context

ADR 0004 deferred the production index until Jira/Slack, authorization, orchestration, and durable
workers were established. Those control-plane foundations now exist. Tactiqo requires Arabic and
English retrieval, strict tenant/hierarchy ACLs, citations, previews, and replaceable embeddings
without restoring the local operational weight of Onyx.

## Decision

- PostgreSQL remains canonical truth for sources, versions, structure, ACL snapshots, and lineage.
- MinIO stores originals and generated previews under tenant-scoped keys.
- PostgreSQL full-text search and pgvector form a derived hybrid index.
- Embeddings are produced only through Embedding Bank and identified by immutable embedding space.
- Every lexical/vector query applies tenant, subject, project, classification, lifecycle, and
  retention predicates before candidates can reach reranking or model context.
- `KnowledgeSearchPort` remains the only retrieval dependency used by agents.
- Index rows are rebuildable; source records and ACL snapshots are authoritative.

## Consequences

This introduces the pgvector extension but no second canonical datastore. New embedding providers
or dimensions create a new embedding space and parallel index; they do not rewrite agent code.
Revocation is enforced against current canonical ACL state even when a derived index is stale.

