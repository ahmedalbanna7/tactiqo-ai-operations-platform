# F7 — ACL-aware Multilingual RAG

Status: F7.1 and core F7.2/F7.3 operational; advanced enrichment, preview, and evaluation remain.

## Scope and assumptions

Build the RAG inside Tactiqo using PostgreSQL/pgvector, MinIO, Unstructured/native parsers, and the
existing Embedding Bank. Arabic/English and mixed-language content are first-class. Onyx remains
removed by ADR 0004; ADR 0009 records the selected replacement.

## Repository assessment

Uploads, tenant-scoped originals, checksums, parsing worker, canonical elements, lexical development
search, citations, and document-injection scanning exist. Missing production concerns are sources,
versions, chunks, ACL snapshots, sync checkpoints, previews, hybrid indexes, reranking, evaluation,
and revocation propagation.

## Architecture and affected modules

`knowledge/domain` owns provider-neutral source/version/chunk/ACL/lineage values. PostgreSQL stores
canonical metadata and derived indexes, MinIO stores binaries, and `KnowledgeSearchPort` isolates
agents from retrieval implementation.

## Data and migrations

F7.1 adds source, version, chunk, ACL snapshot, and synchronization checkpoint tables. Existing
documents remain compatible and are migrated incrementally. No cross-tenant index namespace or
unscoped query is permitted.

## API, events, jobs, security, and approval

Source administration is manager-controlled; ingestion is asynchronous and idempotent by content
hash. ACL and classification are attached before indexing. Documents are untrusted data, never
instructions. Source deletion, retention changes, legal hold, and ACL expansion require configured
approval and produce sanitized audit events.

## Capacity and failure handling

Parsing, embedding, OCR, and synchronization use F5 jobs with bounded file/record/batch sizes,
checkpointing, retry, and DLQ. Canonical truth may be ready while an index is degraded; the system
reports this honestly and never bypasses ACLs through fallback.

Current local upload limit is 100 MB (raised from 20 MB) while ingestion continues asynchronously.
This is a temporary bounded test allowance, not unlimited processing. Before production or larger
files, add resumable multipart uploads directly to private tenant storage and a durable F5 worker job
for validation, parsing, embeddings, progress, retry and cancellation. The final size/compute limits
must be tenant-policy and quota controlled rather than hard-coded in the chat UI.

## Verification

Unit/integration/evaluation gates cover Arabic, English, mixed text, tables, malformed input,
injection, tenant/department/team/project/user isolation, revocation, citation resolution, preview
boundaries, retrieval quality, latency, and embedding-space cutover.

## Operational checkpoint — 2026-09-14

Migration `20260914_0009` is applied. New ingestion now creates an immutable document version,
normalized language-tagged chunks, and a policy-versioned ACL snapshot in the same transaction that
marks canonical parsing ready. Existing lexical metadata/list/citation reads were tightened from
organization-only filtering to owner-or-authorized-project predicates.

Live ingestion of `F7_IMPLEMENTATION.md` completed through RabbitMQ/Unstructured and produced one
version, 32 chunks, and an ACL snapshot restricted to the originating local user. API and worker
remain healthy. Historical documents are not silently assigned new ACLs; a controlled backfill and
review is required before they enter the production hybrid index.

## Hybrid retrieval checkpoint — 2026-09-14

Migrations `20260914_0010` and `20260914_0011` are applied. PostgreSQL now runs pgvector 0.8.1,
stores tenant-scoped versioned embedding spaces, and has a full-text GIN index. The ingestion
worker embeds current chunks through the configured Embedding Bank in bounded batches. Retrieval
first applies tenant, user, department, team, project, current-version, and classification
predicates, then fuses lexical and cosine-vector ranks using reciprocal rank fusion. Returned
content is wrapped as untrusted evidence before it can enter model context.

The controlled reindex produced one embedding space and 32 vectors. An Arabic semantic smoke test
returned three authorized results with a resolvable document/chunk citation. The explicit lexical
fallback remains available when the embedding provider is unavailable; it uses the same canonical
document scope and never broadens access.

## Secure source preview checkpoint — 2026-09-14

Citation buttons now open a bounded three-chunk preview centered on the cited chunk. Every preview
request revalidates tenant, current document version, user, department, team, project, and
classification scope at query time. Missing and unauthorized sources both return 404 to avoid
revealing hidden existence. The live authorized preview returned chunks 7–9 and correctly marked
chunk 8 as the cited target; the hidden-source smoke test returned 404.

## Evaluation gate checkpoint — 2026-09-14

F7.4 now has deterministic Recall@k, Precision@k, MRR, nDCG, citation correctness, answer
grounding, p95 latency, unauthorized-result, and injection-detection metrics. A fail-closed
activation decision reports every missed threshold. Versioned Arabic, English, mixed-language, and
security-case fixtures plus initial acceptance thresholds are stored under `docs/evaluation`.
Synthetic tests validate the harness; production certification still requires representative
customer documents, scanned/media fixtures, and live revocation/poisoning runs.

## Isolation and poisoned-document checkpoint — 2026-09-14

The final model-context boundary now quarantines suspicious evidence instead of merely labelling
it. This applies to both hybrid retrieval and the lexical fallback. Direct and indirect Arabic and
English instruction-override, tool-control, impersonation, and secret-exfiltration patterns are
covered by regression tests. A non-mutating live run against pgvector and LM Studio returned three
results for the authorized owner, zero for an outsider, zero below the document classification,
and quarantined poisoned evidence. Customer-workspace revocation and connector deletion drills
remain required before the production exit gate.

## Source revocation and stale-index checkpoint — 2026-09-15

Knowledge sources now support an immediate revoke lifecycle. The caller must still pass policy,
must be the uploader or an organization Owner/Admin, and must type the exact filename. Revocation
atomically marks the canonical document revoked and deletes normalized elements and immutable
versions; foreign-key cascades remove ACL snapshots, chunks, and pgvector rows. The MinIO original
is retained for legal/administrative recovery. Revoked documents are excluded from inventory,
retrieval, citations, and preview.

A live disposable upload was processed and revoked. Post-revocation verification showed status
`revoked`, zero versions, zero chunks, zero vectors, and preview returned 404. API, web, and worker
remained healthy.
