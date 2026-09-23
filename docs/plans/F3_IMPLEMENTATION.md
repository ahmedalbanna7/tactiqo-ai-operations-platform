# F3 Replaceable LLM and Embedding Banks

## Scope and assumptions

F3 makes LM Studio the first local, subscription-free provider for chat and embeddings.
The Owner-facing AI Settings screen is included so selection is testable without code changes.

## Repository assessment

F2 supplies server-derived Owner/Admin roles, policy versions, Agent Catalog and LangGraph
authorization. F3 replaces direct provider composition with provider-neutral routers while
retaining deterministic behavior for tests and safe degradation.

## Architecture and affected modules

- `ai/domain`: provider, capability, profile, health and embedding-space contracts.
- `ai/application`: LLM/Embedding banks, policy selection and administration ports.
- `ai/infrastructure`: LM Studio OpenAI-compatible adapter and PostgreSQL profiles.
- API/UI: Owner settings, discovery, connection tests, activation and playgrounds.

## Data and migrations

PostgreSQL stores provider/profile metadata and secret references only, never secret values.
Every profile belongs to one organization and activation bumps its policy version.

## API, event, and job contracts

Agent code continues using `ModelProviderPort`. Admin APIs expose masked descriptors, models,
health and test results. Vectors appear only in the Owner test endpoint.

## Security and authorization

Administration is Owner/Admin-only. Fallback never expands residency or classification.
Secrets are write-only references; local endpoints are permitted only in local development.

## Capacity and failure handling

Routers enforce timeout, bounded retry, concurrency and circuit breaking. There is no automatic
cross-provider fallback. Accounting excludes prompts and outputs.

## Human approval

Local activation is immediate and audited. Production activation remains approval-gated.

## Verification and documentation

Contract, routing, outage, timeout, circuit, policy, Arabic/English, embedding-space, API,
frontend build and live LM Studio tests are required before closure.

## Open decisions

LM Studio was explicitly selected by the Owner. The current 12B model may be slow on CPU;
installing a smaller model later requires only a profile change.

## Operational checkpoint — 2026-09-12

The local priority slice is operational. LM Studio serves
`qwen3-vl-8b-instruct` as the active reasoning LLM and
`text-embedding-nomic-embed-text-v1.5` under the `tactiqo-embedding` identifier.
The latter produces 768-dimensional vectors with an immutable embedding-space ID.

The Owner UI can discover loaded models, validate and activate either profile, run
an LLM or embedding playground request, and inspect the 22 effective Agent cards.
The normal chat flow completed through the same AI Bank and LangGraph path. Qwen's
prompt template accepts function schemas; the integrations profile must remain
running for MCP tool discovery.

This checkpoint does not close the entire F3 roadmap. Provider drain/remove,
stream/structured-output conformance, daily quota aggregation, per-agent quality
tiers, and dual-index re-embedding/cutover/rollback remain before the formal F3
exit gate. They are deliberately not represented as complete in the master plan.

## Usability correction — 2026-09-13

LM Studio discovery now uses its typed `/api/v1/models` contract. LLM profiles see
only `llm` models and embedding profiles see only `embedding` models. Activating a
selection persists the exact model key returned by LM Studio; aliases that are no
longer registered are not presented as valid choices.

Activation now prepares the selected model through LM Studio's model lifecycle API
before changing the active database profile. Already loaded instances are reused;
an unloaded selection is loaded first, and a load failure leaves the prior profile
active. This prevents a large model's first-request JIT load from consuming the
LangGraph execution timeout.

LangGraph now applies a deterministic, zero-LLM classifier before retrieval or
planning. Simple conversation routes directly to one answer call. Explicit file or
report questions route through authorized retrieval and then one answer call.
Requests requiring tools or multiple steps retain the Planner; requests combining
evidence and actions retrieve first and then plan. The route and a content-free
reason code are recorded in run events.

Live verification with the warm local Qwen model completed a greeting in about 6.1
seconds with no retrieval or planning event. A direct file question produced a
`knowledge` route and retrieval event with no planning event. Initial loading of the
6.19 GB model took about 93 seconds on this workstation and must not be confused
with per-message reasoning latency.

The current knowledge path is an initial secure foundation, not production-complete
RAG. It supports upload, object storage, parsing, canonical PostgreSQL elements,
scope-filtered lexical retrieval, citations and source metadata. Vector indexing,
hybrid lexical+dense fusion, retrieval profiles, reranking evaluation, complete
source preview, continuous connector synchronization, and Arabic/English retrieval
quality gates remain in F7.

## OpenAI cloud onboarding — 2026-09-14

The Owner UI now supports LM Studio or official OpenAI profiles for both LLM and
embedding capabilities. OpenAI keys are accepted by a dedicated write-only API,
encrypted with the deployment-owned credential key, and replaced by an opaque
`aisec_` reference. Profiles store only that reference; responses expose only a
boolean indicating whether a reference exists. Tenant/provider ownership is checked
before binding a reference, and the official endpoint is fixed to
`https://api.openai.com/v1` to prevent arbitrary egress and SSRF.

Activation performs credential/model discovery plus a minimal capability probe, so
an LLM cannot be activated as an embedding model or vice versa. The prior active
profile remains unchanged on failure. Migration `20260913_0004` adds the encrypted
local-development store; production replaces the store adapter with a managed
secret vault without changing the OpenAI or bank contracts.

Azure OpenAI and generic OpenAI-compatible endpoints remain planned because they
require explicit tenant allowlists, region/residency policy, private endpoint rules,
and provider-specific authentication. Credential rotation/revocation UI and managed
vault adapters also remain before formal F3 closure.
