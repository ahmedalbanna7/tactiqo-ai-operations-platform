# ADR 0003: Production RAG architecture

- Status: Accepted
- Date: 2026-09-09

## Decision

Tactiqo uses a two-plane RAG architecture behind `KnowledgeSearchPort`.

### Ingestion plane

1. The API authorizes upload and stores the immutable original in MinIO.
2. PostgreSQL records canonical identity, checksum, organization, project,
   classification, ACL version, and processing state.
3. RabbitMQ dispatches an idempotent parsing job.
4. An isolated Unstructured worker parses PDF/DOCX/XLSX into canonical elements
   with page, sheet, row, table, heading, and ordinal provenance. Native parsers
   are bounded fallbacks.
5. A content-security scanner labels instruction-like document text without
   deleting evidence or granting it authority.
6. The worker submits canonical sections and non-secret scope metadata through
   Onyx's supported ingestion API. Onyx owns embeddings and its index backend.

### Retrieval plane

1. The server derives `ExecutionContext`; the model cannot supply or broaden it.
2. PostgreSQL computes authorized document scope before retrieval.
3. Onyx performs hybrid retrieval over that scope.
4. Tactiqo revalidates every result against PostgreSQL. Unknown, stale, or
   unauthorized results are discarded fail-closed.
5. Retrieved text is scanned and wrapped as untrusted evidence, never instructions.
6. Stable citations and source preview come from canonical elements/original
   storage after a second ACL check, not from Onyx snippets as source of truth.
7. Response review verifies citation coverage, authorization, and injection signals.

## Embeddings

The initial self-hosted profile is `intfloat/multilingual-e5-base`, supported by
the pinned Onyx release and suitable for Arabic/English evaluation. A release
gate compares it with `openai/text-embedding-3-large` on Tactiqo's bilingual
golden set. Changing model dimensions creates a new index and controlled reindex;
vectors from different models are never mixed.

## ACL contract

Onyx Community Edition permission syncing is not the authorization authority.
Tactiqo owns decisions. Indexed documents carry opaque scope metadata, while
authorization is enforced before retrieval and after result resolution. Explicit
deny and classification checks override allow.

For the Community Edition deployment, each organization uses a distinct Onyx
security principal/index boundary; a single globally privileged service token is
not shared across organizations. The pinned Onyx v4.3.9 deployment owns an
OpenSearch backend. This is an intentional update from the older master-spec
reference to Vespa; `KnowledgeSearchPort` prevents that vendor detail from
crossing into domain code.

## Prompt-injection contract

Document text cannot change policy, reveal secrets, select tools, alter ACL
filters, or authorize actions. Suspicious evidence is retained for audit and
citation, marked with risk signals, bounded in context, and denied access to
tool/control channels.

## Release gates

- bilingual Recall@5, MRR@10, nDCG@10, and citation-locator correctness;
- zero cross-organization/project/classification leakage in negative ACL tests;
- PDF page, Word paragraph/table, and Excel sheet/row preview correctness;
- prompt-injection attack pass rate and grounded-answer abstention;
- ingest-to-search latency and degraded-index observability.

Local lexical search is only an explicitly selected development provider. It is
never a silent fallback when Onyx is enabled and is forbidden in production.
