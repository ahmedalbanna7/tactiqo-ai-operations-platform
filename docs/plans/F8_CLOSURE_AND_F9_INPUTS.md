# F8 closure and F9 inputs

Date: 2026-09-21

## Scope and assumptions

- Close the locally verifiable F8 artifact path without describing catalog-only agents as operational.
- Treat the requested second cloud API as Anthropic Claude. OpenAI and Claude remain replaceable
  adapters behind provider ports; no business service imports vendor SDKs.
- Route document analysis and visual/presentation content by declared capability. When both are
  healthy, use the policy-preferred provider; when only one is healthy and policy-compatible, use it
  as a bounded fallback. Never silently move restricted content to a disallowed cloud provider.
- Personal versus company knowledge is an F9 UI and authorization increment. F8 records the future
  contract but does not weaken current tenant isolation.

## Repository assessment

- Nine agent paths are operational: chat, planner, PMO, knowledge, data analytics, report, document,
  presentation and spreadsheet. Review/safety exists as graph nodes rather than an independently
  dispatched agent. Other catalog definitions are capability placeholders.
- Chat-created PPTX/DOCX/XLSX/Markdown artifacts are live and governed.
- AI Bank currently activates only one profile per capability kind, so it cannot route between two
  cloud providers.
- Knowledge upload currently asks for domain/purpose before file selection and does not persist a
  conversation attachment reference.

## Architecture and affected modules

- `ai`: multi-profile capability routing, OpenAI and Claude adapters, independent write-only secrets,
  provider health and deterministic fallback.
- `agents`: request an AI capability such as document analysis or presentation composition without
  naming a vendor.
- `knowledge` and `chat`: persist an authorized attachment reference after ingestion acceptance.
- `web`: two cloud-provider configuration cards and a post-selection upload metadata dialog.

## Data model and migration impact

- AI profiles gain declared capabilities and routing priority; multiple LLM profiles may be enabled.
- Chat attachments reference a tenant-owned knowledge document and conversation/message, never raw
  object keys.
- F9 knowledge visibility adds owner type (`personal` or `organization`) and owner actor. Promotion to
  company knowledge requires Owner/Organization Admin authorization and an audit event.

## API, event and job contracts

- Provider profile APIs remain write-only for credentials and expose only masked status.
- Upload accepts metadata only after file selection. Successful chat upload emits an attachment event
  and returns safe document metadata.
- Ingestion remains asynchronous. Large or expensive work is dispatched when deterministic limits
  classify it as Background; status is visible through jobs and chat events.

## Security and authorization

- Provider fallback is limited by tenant allowlist, classification, residency and health.
- Company-knowledge promotion is administrative, audited and does not make personal files public by
  default.
- Attachment download and preview always re-authorize the document; chat membership is not authority.

## Capacity, failure and approval

- Provider attempts are sequential, bounded and circuit-broken; no fan-out sends the same content to
  both providers.
- Upload/ingestion failures preserve a safe attachment state. Large files use durable jobs when the
  configured foreground threshold is exceeded.
- External publication and company-knowledge promotion require the configured human approval.

## Verification and documentation

- Add provider routing/fallback, secret non-return, classification denial and accounting tests.
- Add upload-dialog, attachment rendering, direct-object-reference and refresh tests.
- F8 may close locally only after format/security/scope tests pass. Real Jira/Slack/Email success and
  provider reversal remain explicitly external-blocked until tenant credentials and test workspaces
  exist.

## Current provider behavior (2026-09-21)

- LM Studio remains enabled for chat, planning, artifact text composition and embeddings.
- OpenAI and Claude have independent Settings cards, encrypted credential references, model discovery,
  validation, enable and disable actions. Enabling either LLM gives it priority on the next request;
  disabling it returns routing to the next eligible provider, including local LM Studio.
- Capability policy prefers Claude for document analysis and OpenAI for presentation composition when
  priorities are equal; each actual request is sent sequentially to one provider at a time.
- Cloud LLM profiles default to `public` and `internal` classifications. Confidential and restricted
  requests continue locally until an explicit reviewed external-data policy is implemented.
- Provider fallback is not a promise that every external failure can be retried safely; no cloud
  credential is installed, so real OpenAI/Claude calls remain unverified.
- Local verification: routing/disable and artifact unit tests, API tests, TypeScript, Docker image
  build, migration `20260921_0020`, healthy API/web containers. This does not close external tests.

## F8 exit-gate audit (2026-09-21)

**Decision: F8 remains open.** The master plan explicitly includes execution families that are not
implemented. Passing a local test suite must not be interpreted as their completion.

| Gate | Verified state | Remaining acceptance work |
| --- | --- | --- |
| Native office draft path | DOCX/PPTX/XLSX render and security regressions pass | PDF output, visual QA, rich Office templates/notes/charts |
| Artifact governance | Versioning, review gates, storage, metering, Legal Hold and dry-run actions exist | Positive independent two-person publication and full policy matrix |
| External actions | Tenant MCP mapping, preflight, retry and compensation contracts exist | Real Jira/Slack/email tenant OAuth/grants, destination checks, verified success and reversal |
| Execution agents | Report/document/presentation/spreadsheet paths work | Email, Power BI, automation, image, video, meetings, data operations and social flows |
| Scope isolation | Existing authorization and negative tests pass | Per-agent department/data/tool/action boundary certification |
| Regression suite | `backend/tests/unit`: 129 passed; F8-focused subset: 32 passed | Full integration, visual, real-provider and human-review E2E tests |

Do not change the master-plan F8 checkboxes to complete until each remaining item has implementation,
tests and required real-world tenant evidence. Missing third-party credentials and a second authorized
reviewer are external prerequisites, not test results.

## F9 committed inputs

1. Separate **My Knowledge** and **Company Knowledge** navigation and APIs.
2. Only Owner/Organization Admin can promote or upload organization-wide knowledge.
3. The current uploader chooses domain and purpose in a dialog after selecting the file.
4. Files uploaded from chat remain visible as attachment cards and continue ingestion into the
   authorized knowledge scope.
5. Company Settings exposes knowledge ownership, ACL inheritance, classification and indexing health.
