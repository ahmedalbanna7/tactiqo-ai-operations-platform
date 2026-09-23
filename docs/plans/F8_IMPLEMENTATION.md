# F8 — Execution agents and artifact production

Status: F8.1 core foundation operational; lifecycle expansion and execution agents remain.

## Scope and architecture

F8 turns authorized plans into governed business outputs. The `artifacts` modular-monolith boundary
owns provider-neutral artifact identity, immutable versions, classification, scope, citations, data
lineage, and lifecycle. Format implementations are adapters registered through
`ArtifactRendererRegistry`; adding PowerPoint, Word, spreadsheet, image, video, or BI renderers does
not change the application service.

## Data, storage, contracts, and security

Migration `20260915_0012` creates tenant-scoped `artifacts` and immutable `artifact_versions`.
Rendered bytes are private MinIO objects; PostgreSQL remains lifecycle and lineage truth. Reads
apply organization plus owner/project scope before resolving a storage key. Downloads reauthorize,
verify SHA-256, and return no storage credentials. Outputs start as `draft`; no renderer can publish
or communicate externally implicitly. Platform citations must use `tactiqo://knowledge/`.

## Capacity, approval, and failure behavior

Draft input is bounded to 200,000 characters and 100 citations/lineage references at the API.
Storage or persistence failure is reported; external publication is not attempted. Review,
compute/provider/cost accounting, retention enforcement, and compensation workflows remain
explicit F8 increments before any execution agent may send or publish.

## Verification checkpoint — 2026-09-15

Renderer registration, draft-only state, private object storage, checksum-verified download, and
invalid citation rejection have unit coverage. Ruff, mypy, and 111 tests pass. Migration
`20260915_0012` is live. A smoke report was created as draft version 1, returned through the scoped
artifact list, and downloaded with HTTP 200 and a matching 38-byte object. API is healthy.

## Review and publication checkpoint — 2026-09-15

Migration `20260915_0013` adds one immutable review decision per artifact version. Draft owners can
submit a version for review. Only organization Owners/Admins may decide or publish, and the
requester can never approve their own version even when they also hold Owner. Rejection returns the
artifact to draft; approval is the only route to publish. Row locks and state preconditions prevent
duplicate or stale transitions.

The live smoke artifact moved to `in_review` with a pending decision. Self-approval returned 403 and
publication without approval returned 409. The API remained healthy. A second real organization
reviewer is required to exercise the positive approval/publish path without weakening separation of
duties.

## Organization output-policy checkpoint — 2026-09-15

Migration `20260915_0014` adds one tenant-owned artifact policy with bounded brand name, footer,
classification-mark requirement, retention-day setting, and monthly artifact limit. Owner/Admin
API operations can read and replace that policy. Draft creation reads it server-side, rejects work
after the tenant monthly limit, and applies brand, classification, and footer outside model-owned
content. This prevents prompts or renderers from silently removing required markings.

The live policy was saved for the local tenant and a new report draft was generated and downloaded.
Its bytes contained `# Tactiqo Operations`, `Classification: INTERNAL`, and the configured footer.
Migration head is `20260915_0014`; seven focused artifact/API tests pass, Ruff passes, and mypy
passes. The retention value is configuration only at this checkpoint: scheduled purge, legal hold,
template catalog, compute/provider metering, monetary cost accounting, retention enforcement, and
legal-hold controls remain open.

## Policy UI checkpoint — 2026-09-15

Company Settings now exposes a separate Arabic-first output-policy tab. It loads the effective
tenant policy, edits only the bounded public fields, and persists through the Owner/Admin API. The
screen explicitly distinguishes configured retention days from the not-yet-active purge/legal-hold
workflow. API errors do not expose secrets or hidden organization data. TypeScript, ESLint, and the
production Next.js build pass, and the rebuilt web container is running on port 13000.

## Templates and metering checkpoint — 2026-09-15

Migration `20260915_0015` adds tenant-owned artifact templates, artifact retention/legal-hold
columns, append-only usage facts, and an idempotent external-action ledger. Report templates require
exactly one `{{content}}` slot, are resolved through tenant scope, and are applied before server-owned
brand and classification markings. Current-month APIs return artifact count, stored bytes, model
units, and estimated-cost micros without artifact content. The Settings UI lists usage and lets an
Owner/Admin create report templates.

A live template was created and used to render a private draft; the downloaded bytes contained the
template structure and the usage ledger recorded one artifact and 144 bytes. Migration head is
`20260915_0015`. Legal-hold and purge service operations, richer format templates, and population of
model-unit/cost fields from provider execution remain in progress.

## Retention and execution-control checkpoint — 2026-09-15

Every new artifact now receives an absolute UTC retention deadline from the tenant policy. An
Owner/Admin can place or release Legal Hold. Bounded purge claims only due, unheld rows with
`SKIP LOCKED`, revokes them before object cleanup, deletes exact MinIO keys idempotently, and records
`purged_at` only after successful cleanup; metadata and lineage remain for audit. A live due artifact
was protected during hold, purged after release, and its authorized download changed to 404.

The renderer registry now supports governed draft creation for report, document, presentation,
spreadsheet, image, video, email, Power BI, and automation families. These are provider-neutral text
draft contracts, not claims of native media generation. Action preflight validates approved-artifact
state, action, destination type/value, and a tenant-scoped idempotency key; only a destination hash is
stored. A live email and presentation draft were created, and repeating one email preflight returned
the same action ID without sending externally. Provider execution, result verification and
compensation remain open until their adapters are implemented/configured.

## Provider execution checkpoint — 2026-09-16

Validated actions can now be atomically claimed, executed through an `ArtifactActionProvider`,
verified, and finalized as succeeded or failed with sanitized error codes. Concurrent/repeated calls
return the durable state rather than causing a duplicate side effect. The destination plaintext is
re-hashed and must match the preflight record before the action can be claimed. The initial
`dry_run` provider produces deterministic verified external identifiers and performs no external
side effect, giving the UI and tests a complete safe flow while real provider credentials are absent.
Real Jira/Slack/email/media adapters, bounded retry scheduling and persisted compensation tokens
remain the next increments.

Migration `20260916_0016` adds bounded attempt counters and provider compensation references.
Explicit retry can return only failed actions below their persisted maximum to validated state.
Compensation is accepted only for a succeeded action, invokes the original provider, and is itself
idempotent. Live dry-run execution completed with attempt `1/3`; repeated execution did not increase
the counter, and repeated compensation remained `compensated`.

## Native Office and artifacts UI checkpoint — 2026-09-16

Document, presentation, and spreadsheet execution agents now have real DOCX, PPTX, and XLSX
renderers behind the same registry. Generated packages contain no macros or external links;
spreadsheet values beginning with formula control characters are neutralized. Automated tests inspect
the Open XML ZIP structure and formula safety. Live downloads produced valid `PK` packages of 36,659,
29,161, and 4,975 bytes respectively.

The Arabic-first Artifacts drawer lists only scoped outputs and supports authorized download, review
submission, independent approve/reject, destination preflight, and safe dry-run execution with visible
attempt state. API and Web are healthy. Image/video/native PDF and real external provider adapters
remain open rather than being represented as complete.

## Tenant MCP execution checkpoint — 2026-09-16

External artifact actions can now select the `mcp` provider through an explicit tenant-owned mapping
from action and destination type to one qualified MCP tool and its destination/content argument names.
Execution re-resolves the tenant connection and OAuth/credential state, lists the caller-visible tools,
and checks the effective grant immediately before the call. Missing mappings, disconnected providers,
revoked grants, and hidden tools fail closed; no destination plaintext is persisted.

Settings exposes mapping activation/deactivation, while the artifact drawer exposes Dry-run/MCP
selection, bounded explicit retry, attempt state, and compensation. A live deliberately unavailable
Slack mapping failed closed with `provider_execution_failed`, and that synthetic mapping was disabled
after the test. This validates denial behavior only: no claim is made that Jira or Slack external side
effects succeeded without a real tenant connection, OAuth consent, exact tool grant, and destination.
Real-provider compensation also remains unavailable until an explicit reverse-tool mapping exists.

## Chat-to-artifact execution checkpoint — 2026-09-16

The deterministic classifier now recognizes explicit PPTX, DOCX, XLSX, and Markdown creation
requests before model planning and assigns the least-privileged presentation, document,
spreadsheet, or report execution agent. LangGraph prepares bounded content, creates a governed
tenant-scoped draft through `ArtifactService`, and emits `artifact.created` with safe metadata and
an authorized download route. The chat UI renders the file card immediately and persists only a
non-secret artifact reference so the download remains available after refresh. Discussion-only
mentions such as "what is PPTX?" do not create an artifact or consume tenant quota.

A live Docker smoke created and downloaded a 31,369-byte PPTX with a valid `PK` package signature
from an Arabic chat request. Artifact review, publication, retention, quota, ACL scope, and checksum
verification remain enforced by the existing artifact boundary.
