# F9 implementation record

Date: 2026-09-21. F9 is active. Remaining F7/F8/F9 product closure is scheduled in F11 and tracked
in `DEFERRED_PRE_F9_BACKLOG.md`.

Latest checkpoint: 2026-09-23.

## Scope and assumptions

Build the employee and Company Settings experience incrementally. Keep the existing chat-first
flow. The first increment focuses on truthful effective-agent visibility, clear jobs/artifacts,
and a secure distinction between personal and company knowledge. Remaining settings modules
follow the F9 checklists in the master plan; do not mark F9 closed prematurely.

## Repository assessment

The UI currently has one Knowledge drawer and several separate Settings/Integrations/Jobs/Artifact
drawers. Upload metadata is already chosen after file selection and chat attachments persist. Agent
cards come from a server-filtered endpoint. Documents are actor-scoped or project-scoped; there is
no explicit company-knowledge owner scope or promotion API yet.

## Architecture and contracts

- Frontend: accessible Arabic-first navigation; employee view shows only server-returned cards;
  Company Settings uses server-side entitlements, not merely hidden buttons.
- Knowledge: canonical document ownership scope, tenant-safe listing, authorized promotion,
  revalidated retrieval/preview and audit. Existing personal documents must remain personal.
- API: separate personal/company list/upload operations, with manager-only company mutation.
- Jobs: existing durable job IDs, states and progress are the API truth; UI cannot invent progress.
- Provider/MCP/artifact settings continue through existing guarded application services.

## Data and migration

An explicit knowledge ownership field defaults to personal for existing rows. Company promotion
must update canonical ACL/index evidence transactionally or leave the document unavailable until
reindex succeeds. No migration may make existing personal rows company-wide.

## Security and human approval

All Company Settings reads/mutations require server-derived role/entitlement checks. Promotion is
high-impact; require an explicit confirmation, audit, and policy review before broadening readers.
Search, citation preview, downloads and chat attachment display must use the same scope decision.
No hidden document name/count may leak to an unauthorized user.

## Capacity, failure and tests

Paginate bounded lists, preserve asynchronous ingestion, show real status and safe errors. Add
API-negative and UI entitlement tests, stale/concurrent mutation tests, keyboard/RTL/responsive
checks, and an end-to-end owner setup flow. A failure must not leave half-promoted visibility.

## This continuation's bounded scope: organization-admin HTTP denial matrix

- Scope: extend route-boundary regression tests so ordinary employees are denied across the
  company directory, hierarchy, membership, role, and lifecycle management API surface before any
  repository is touched. Do not add or broaden privileges.
- Assessment: routes delegate authorization to `OrganizationAdministrationService`, which checks
  the server-derived role before its repository calls. Existing tests prove only access-preview
  denial; the settings/admin route family needs equivalent regression coverage.
- Architecture/API/data: strengthen the authorization service's access-preview validation order and
  exercise existing HTTP contracts; no schema, public API, event, or job change is planned.
- Security: use an uninitialized service test double whose repository cannot be reached if service
  authorization ordering is correct; a repository call must fail the test. Use employee context
  derived by the test resolver, not request-supplied role claims.
- Capacity/failure: local ASGI transport and fixed small request set; no database, external IdP or
  provider dependency.
- Human approval: none; this adds regression coverage without changing effective policy.
- Verification: targeted and full pytest, Ruff, mypy, diff check. Preview scenario shape is rejected
  after administrator authorization but before target lookup, policy catalog access, or tool reads.
  Remaining stale/concurrent-write and full owner configuration flow gates are tracked separately
  and will not be marked complete.

## Latest continuation checkpoint: admin-route denial and preview validation

## Docker-backed closure-gate review (2026-09-23)

Plan sequencing decision: F9 is not being represented as complete; its remaining product closure
gates are transferred to F11 after F10 operational hardening, as requested. The original F9 exit
criteria remain authoritative.

- With Docker access explicitly authorized, `docker compose ps` reports API, PostgreSQL, Redis,
  RabbitMQ, MinIO and web healthy; MCP demo and worker are running. `/health/ready` reports healthy,
  the dashboard returns HTTP 200, and `alembic current` reports `20260922_0022 (head)`.
- The read-only browser smoke for membership access preview succeeded; it made no membership or
  permission changes. The full suite checkpoint remains 183 passing tests; Ruff/mypy for affected
  backend/API files and frontend TypeScript/production build were previously verified.
- This operational check does not satisfy F9 closure. Remaining blockers are: company-wide versus
  department/team knowledge readership decision; effective tool-grant editing and policy reasons;
  source/document/resource ACL explanation and preview; remaining catalog, quota, budget and
  approval settings; destructive/stale/concurrent mutation tests; broader Owner/Admin/employee UI
  entitlement and negative-path certification; formal accessibility and cross-browser audit; and
  end-to-end company setup with a configured real OIDC provider and at least two roles.
- No product policy, account, membership, connector grant, or persisted production data was changed
  during this verification. F9 stays active; Docker health alone is not a phase exit gate.

## Continued authorization-boundary increment (2026-09-23)

- Extended API denial coverage from company structure/people routes to invitation management,
  agent-catalog administration, company-knowledge promotion and organization MCP connection
  creation. The company-knowledge inventory remains governed by document ACL rather than an
  assumed admin-only rule, so it is intentionally not included in a blanket denial assertion.
- The new negative HTTP test exposed that organization-scoped Jira/Slack connection creation raised
  `IntegrationAdministrationDeniedError` without mapping it to a safe HTTP response. The route now
  returns a generic 403. Company knowledge promotion/revocation permission denials also use the
  generic administration response rather than returning internal policy reason strings.
- Verification: focused HTTP boundary suite 20 passed; complete repository suite 191 passed; Ruff
  passed for changed API files; web TypeScript check and `git diff --check` passed. Mypy was started
  but did not complete within this Windows runtime window, so it is not claimed for this increment.
  API and migration images rebuilt; compose migration completed, API started, and health check is
  healthy; readiness, OpenAPI and dashboard all returned HTTP 200.
- Added explicit HTTP checks that an Organization Admin is denied the Owner-only role grant,
  suspension, and revocation routes even when those routes request step-up assurance. The focused
  API boundary suite is now 23 passed and the full suite is 194 passed; Ruff and `git diff --check`
  pass. This is test-only after the API image rebuild.
- No grants, memberships, knowledge documents, connections, or other application records were
  changed by tests. This is a security-hardening increment, not F9 closure.

- Added ten parameterized HTTP denial cases for company unit/people listing, department/team/project
  creation, unit membership, privileged role assignment, member suspension, role-history listing,
  and role revocation. The employee context is server-derived; each route returns the same generic
  403, and the uninitialized administration test service proves repository access is not reached.
- Invalid/incomplete role-preview scenarios now fail after administrator authorization but before
  delegated target lookup, agent policy evaluation, or integration-grant reads. Valid/no-change
  role semantics still depend on the target's server-resolved role set.
- No production data or access grants were changed. No migration, external service, event/job, or
  API schema changes were made. This narrows but does not complete the F9 negative-path gate.
- The expanded mypy target exposed that the existing organization-administration test repository
  double omitted two read methods from its declared protocol; the fake now implements those unused
  methods explicitly so strict typing checks the full identity test surface.

## This continuation's bounded scope: read-only organization-membership preview

- Scope: extend effective-access preview to compare current agent access with one hypothetical
  department/team/project membership add or removal, independently from role simulation.
- Assessment: the resolved employee context already carries server-derived department, team and
  project IDs; the policy compiler evaluates these attributes. Existing previews expose only role
  deltas. The unit hierarchy is tenant-owned and teams/projects are department-bounded.
- Architecture: add an application port plus SQL adapter to validate the selected unit by exact
  tenant and return its owning department/descendants; apply the hypothetical change to an immutable
  context copy and reuse the existing policy-backed agent catalog. Add one optional request scenario
  and response delta contract, and expose it in the existing employee access-preview dialog.
- Data/API/jobs: no migration, durable mutation, event or job. The API request remains bounded to one
  typed scope change. Role and membership scenarios will not be combined in one request.
- Security: Owner/Admin gate remains first; invalid scenarios are rejected before target policy
  evaluation; a tenant-missing unit returns a generic invalid-scenario response. Team/project add
  requires the target's department membership. Removing a department removes descendant team and
  project IDs from the simulated context only. Tool grants remain explicitly current-state and
  source/document ACL is not simulated.
- Capacity/failure: one bounded SQL read of the selected unit plus children when needed; no provider
  or model calls. SQL failures fail the preview safely.
- Human approval: none; this is non-persistent simulation. Any actual membership mutation is outside
  this scope and remains governed by the existing guarded administration service.
- Tests: validate hierarchy, tenant isolation, no-op cases, immutable current context, gained/lost
  agents/actions, unauthorized requests, typed API contract and UI behavior. Rebuild API/web and
  check readiness after implementation.
- Verification: full repository suite 173 passed; Ruff passed and mypy passed on 42 authorization,
  identity, API and test files; `git diff --check` passed. API and migration images rebuilt; migration
  completed, all Compose services report healthy, `/health/ready` reports PostgreSQL/Redis/RabbitMQ/
  MinIO healthy, and the dashboard returns HTTP 200. A live API request with an incomplete preview
  scenario returned 422 against a nonexistent target, confirming validation precedes delegated
  target lookup.

## Implemented checkpoint: organization-membership policy simulation

- Effective-access preview now accepts one mutually exclusive hypothetical role or membership
  change. Membership scenarios support adding/removing a department, team, or project; only active
  units are resolved from the exact organization. Team/project additions require the employee's
  existing department membership. Simulated department removal also strips that department's team
  and project descendants from the copied context. No role or membership is written.
- The service reports scenario type plus proposed unit kind/id/operation and computes gained/lost
  agent cards and actions using the existing policy compiler. Jira/Slack grants remain current-state
  only; knowledge source/document ACL and row-level data scopes are explicitly not simulated. UI
  labels communicate those limits and allow one scope selection from company units.
- Unit tests cover role/current paths, team add/remove, project add/remove, department removal with
  child-scope cascade, invalid cross-department add, no-op scenarios and context immutability. SQL
  adapter tests assert exact tenant bind predicates for all unit kinds, include inactive descendants
  for department removal, and skip child queries when the department is unavailable. Browser smoke
  exercised the membership selector and department-add comparison against the local company; API
  returned 200 and a membership scenario without gained/lost cards for that sample.
- Verification checkpoint: full suite 183 passed; Ruff and mypy passed on the affected authorization,
  identity adapter, API and test files; frontend standalone TypeScript and the Next production build
  passed. API/web containers were rebuilt; live health checks and UI membership simulation passed.
- This remains a bounded F9 capability, not phase closure. Policy reason codes, tool-grant what-if
  simulation, resource/source ACL simulation and product scope policy remain.

## Open external decisions

Company-wide default readership versus department/team-restricted ACL needs a defined policy.
Until then, company scope must be explicit and conservatively authorized, not inferred from an
admin upload. Real multi-user certification needs at least two user accounts/roles.

## Completed bounded increment: effective integration-grant preview

- Scope: show a selected employee's already-effective Jira/Slack tool grants inside the existing
  admin access preview. This is a read-only inventory, not an MCP discovery call or an edit
  simulation; tool grants currently bind to org/user/department/team/project, not role.
- Assessment: tool execution filters active tenant-visible connections and resolves grants from
  server context. Existing `list_active` carries encrypted credentials, so the preview must use a
  new metadata-only connection query and must never pass credentials into its response.
- Architecture: add a bounded metadata query to the integration repository; an infrastructure
  adapter implements the authorization preview's tool-access read port; the existing preview
  service combines it with allowed-agent results; the API schema/UI render provider, connection
  label, tool name, and permission only.
- Data/API: no migration or event/job change. Extend `POST /company/people/{id}/access-preview`
  with a bounded `tool_grants` collection and `tools_truncated` indicator.
- Security: retain Owner/Admin check, standard-assurance delegated target context, tenant/connection
  visibility and effective-grant predicates. Omit endpoint URLs, IDs, credentials, tool schemas,
  disabled/revoked connections, and unmatched grants. No provider network traffic.
- Capacity/failure: cap visible connections and response grants; if the optional integration
  subsystem is disabled, return an empty list. Query failures fail the preview safely rather than
  returning an incomplete result as complete.
- Approval: none; there are no mutations. Any future proposed grant edits require a separate,
  explicit design and approval workflow.
- Tests: coverage now verifies connection visibility/target membership filtering, connection and grant
  capping/truncation, no credential projection, and standard-assurance target-context passthrough.
  Browser smoke verified that an Owner can open the selected employee access preview, view the
  effective tool-grant section, and compare a role scenario without persisting changes. No matching
  grants are shown as an empty list; the browser smoke did not create or alter any grants.
- Open decisions: no role-based tool grant model exists; simulate org-unit membership changes and
  grant policy edits only after an explicit policy semantics decision. Knowledge-source ACL preview
  remains separate because those grants are governed by document classification/owner/project ACL.

## Implemented checkpoint

- Migration `20260921_0021` defaults all old rows to personal and old ACL snapshots to no
  organization-wide access. New company uploads require Owner/Admin. Promotion requires exact-name
  confirmation and atomically updates current ACL evidence plus audit.
- Retrieval, lexical fallback, source inventory and citation preview use tenant, classification and
  document ownership gates; the UI fetches personal/company lists separately.
- Effective agent discovery excludes catalog-only agents; background jobs no longer show a fabricated
  percentage when no total is known.
- Company Settings navigation is server-derived for currently implemented destinations, with a
  minimal overview. An Owner/Admin can list/create departments, teams and projects through the
  tenant-safe Company Structure screen, select verified managers and assign members. The bounded
  people directory shows active roles and classification. Invite links are now supported.
- This is a verified F9 increment, not the F9 exit gate. Role/status administration,
  complete agent catalog controls, richer ACL preview/approval, policy simulation and browser-level
  accessibility/negative-path certification remain open.
- Agent-assignment directory and guarded UI now support department/team/project/user grants and
  revocation. Assignment reads are bounded and tenant-scoped; they omit tool/connection secrets.
  Deployed image smoke checks returned HTTP 200 for the assignments endpoint and settings navigation;
  all compose services are healthy. Full agent catalog management, tool/quota/approval editing,
  policy preview, browser accessibility, and an end-to-end setup gate remain open.
- Chat now renders the server-compiled work class, step count and operational agent while a run is
  active. It intentionally does not disclose internal source/tool identifiers. Detailed per-step
  state and explicit data-reader display remain open.
- Owner/Admin can now generate a department-bound invite link without sending email. The token is
  carried in the browser URL fragment, removed from the address bar, and sent in request bodies so
  it does not enter HTTP request paths or referrer headers. Only its SHA-256
  digest is stored; it expires after 72 hours, is single-use, can be revoked, and OIDC callback
  atomically creates the employee membership/department assignment and consumes the invite. The
  local API smoke test created, inspected and revoked a link; after revoke, preview returned not
  found. OIDC itself is disabled in this local setup, so a real IdP acceptance was not exercised.
- Migration `20260922_0022` is applied and `alembic current` reports it as head. OIDC must be
  configured for invite acceptance; this local environment only verified invitation create, preview,
  listing and revoke because its OIDC login is disabled.
- Owner-only, step-up protected member suspend/reactivate controls are now wired end to end. A
  suspension atomically changes tenant membership, revokes that member's tenant sessions and writes
  a secret-free audit event. Concurrent owner changes lock the tenant row; the final active Owner
  cannot be suspended or have their Owner assignment revoked. Self-suspension is denied.
- The people screen now lists bounded role-assignment history, supports guarded grants of
  organization-admin/integration-manager roles and revokes non-Owner role grants. Every operation
  remains server-authorized; role changes require Owner + step-up. The standard request context now
  honors role effective dates and active department membership; team/project membership uses the
  effective fields available in their current schema.
- Added `Preview access` for a selected member. It resolves that member's live, tenant-scoped
  context at standard assurance (no session impersonation), then calls the same agent policy
  compiler used for effective cards. It compares current access with a hypothetical add/remove of
  one existing non-Owner role, shows current/proposed allowed agents and actions, and lists gained/
  lost agents; the simulation never saves the role change. Missing or suspended members produce the
  same safe not-found response. Service tests cover standard-assurance resolution, role-diff
  behavior, and denial of non-admin probes before target lookup.
- Company Agent Settings now includes a bounded, admin-only catalog of definitions and immutable
  versions, plus install-disabled-by-default and enable/disable controls. API smoke verification
  showed 35 catalog entries, and only exposes safe definition/version/lifecycle metadata.
- The access preview supports role-derived scenarios only, not hypothetical edits to department,
  team, project, tool, or knowledge ACL policies. It now lists current effective integration tool
  grants, but does not explain their policy reasons, knowledge-source categories, or row/document
  scope; do not interpret it as a complete authorization audit.
- Bulk policy evaluation now loads one tenant rule snapshot per evaluation phase and batches audit
  writes, preserving per-action decisions while removing hundreds of database round trips from
  agent discovery and preview. Local owner preview with 35 agents completed in 1.49 seconds after
  this change (previous per-decision audit path took over 20 seconds in the same local stack).
- Latest verification: 152 repository tests pass; Ruff and mypy pass for affected backend/API files;
  standalone TypeScript check passes. After the access preview addition, the full suite has 149
  passing tests. Docker production builds completed; API and web containers are healthy; local live/
  ready/web/company-people/access-preview/catalog HTTP checks returned 200, unknown-member preview
  returned 404, the catalog returned 35 entries, and the preview returned 35 allowed agents for the
  local owner context. Browser automation and
  full multi-user end-to-end OIDC acceptance remain unverified because local OIDC is disabled.
- F9 remains active and is not closed: department/team/project/tool/knowledge policy simulation,
  tool policy-reason and source/resource-scope explanations, remaining catalog/tool/quota/approval
  settings, formal browser accessibility and multi-role negative-path certification, and a full
  owner setup E2E gate remain.
- Continuation verification: the complete repository suite passed locally (152 tests), focused
  authorization/catalog tests passed (18), Ruff passed for the affected authorization/catalog/API
  surfaces, and `git diff --check` was clean. After obtaining Docker access, all compose services
  reported healthy; API live/ready returned `healthy`, and the dashboard returned HTTP 200. The web
  image build completed from cache. A standalone frontend TypeScript check remains unavailable in
  this host/container setup (`tsc`/`pnpm` are not on the active runtime PATH); this is not claimed
  as an independent typecheck pass. F9 remains open.
- Current-access preview now avoids a second identical policy/catalog evaluation when no proposed
  role change was requested. A real role simulation still evaluates both current and proposed
  contexts. Unit coverage asserts exactly one evaluation for current-access preview and two for
  role simulation, preventing duplicate audit/database work on the common preview path.
- This increment changed application logic and tests only; no schema migration or permission policy
  was changed. Full tests (152), Ruff, mypy on the changed module/tests, and `git diff --check`
  passed. API image was rebuilt and the service is healthy; readiness reported PostgreSQL, Redis,
  RabbitMQ and MinIO healthy, and the web dashboard returned HTTP 200.
- Access preview now reports gained/lost actions for agents that remain visible across a simulated
  role change, separately from whole-agent gain/loss. The employee UI displays these action-level
  deltas. No permission is changed by this simulation.
- Integration inspection confirmed current grants are filtered by active tenant-visible connection
  and server-derived organization/user/department/team/project membership, then checked by the MCP
  gateway at discovery and call time. Preview intentionally does not call external MCP servers:
  discovery would add network latency and provider dependence to an admin preview. Effective
  connection/tool grant summaries are now implemented; proposed scope edits and knowledge-source
  category/document ACL explanations remain follow-up work. This is not a live provider discovery or
  complete authorization simulation.
- Verification of action-delta increment: full test suite 152 passed; Ruff and mypy passed on
  affected files; production Next.js build completed with TypeScript; rebuilt API/web are healthy,
  readiness dependencies are healthy, dashboard HTTP 200, and OpenAPI publishes the new
  `action_changes` response field. `git diff --check` is clean.
- The access preview now adds a read-only, bounded summary of active effective Jira/Slack tool grants.
  It uses a dedicated metadata-only SQL projection and never loads the encrypted authorization
  column, contacts MCP providers, or returns endpoints, connection IDs, credentials, or tool schemas.
  It resolves grants against the selected employee's server-derived standard-assurance tenant
  context, and reports truncation explicitly. If integration support is disabled, the list is empty.
  Role simulation does not change tool grants because the current grant model is scoped to org/user/
  department/team/project, not roles; the UI states this limitation.
- Latest verification for this increment: repository test suite 157 passed; Ruff passed across the
  affected authorization/integration/API surfaces; `git diff --check` clean. Browser smoke covered
  the owner access-preview and role-comparison flow read-only. A fresh read-only Docker/API check
  confirmed API readiness healthy, web HTTP 200, and OpenAPI advertises both new response fields;
  all relevant Compose containers reported healthy. No new image build was required for this doc and
  test-double-only follow-up.
- Follow-up hardening: API-level denial tests now exercise the HTTP boundary (unauthenticated
  preview returns 401 before resolving a target; an employee receives a generic 403 before target
  lookup/catalog reads). The long access-preview dialog is bounded and internally scrollable, so
  its close control remains reachable. Closed drawers are removed from keyboard/screen-reader flow;
  knowledge scope navigation has roving focus, Home/End and RTL-aware arrow handling; settings
  navigation now uses navigation semantics rather than pretending separate drawers are tabs.
  Responsive/browser smoke found and fixed mobile topbar overflow; widths 320, 390, 760, 768, 900,
  1024 and 1280 px were checked with no document horizontal overflow. Knowledge keyboard navigation,
  preview scrolling/closing, and the current employee access preview were exercised read-only.
- Latest verification: full repository suite 159 passed; Ruff passed on affected auth/integration/API
  surfaces; mypy passed on 37 affected source/test files; Next.js production build and TypeScript
  completed; Compose services report healthy and API readiness/dashboard HTTP checks pass; `git diff
  --check` is clean. These checks improve the F9 verification gate but are not formal WCAG or complete
  cross-browser certification.
- F9 remains open and is intentionally scheduled for closure in F11 after F10 operational
  hardening: effective tool scope editing and source/resource-ACL
  explanation, full agent catalog/tool/quota/approval settings, formal accessibility audit and
  cross-browser certification, destructive/stale/concurrent mutation tests, broader multi-role API
  negative-path certification, and a full owner setup E2E gate remain. The company-wide versus
  department/team default readership policy also requires an explicit product decision.

## Employee experience follow-up — initial UI increment

- Replaced the always-visible company-settings drawer entry with a company-settings action under the
  profile menu. It is rendered only when server-derived company settings navigation grants at least
  one section; the server remains authoritative for every API request.
- Added a separate personal-preferences dialog with browser-local display name/photo, language and
  light/dark theme preferences. These values are not sent to the API and do not represent an account
  profile or cross-device settings service. Only small raster image uploads are accepted for the
  local avatar.
- Added an initial notification center derived from authorized visible job, artifact-review and
  integration status responses. Read state is browser-local; durable server-side notifications,
  cross-device read state, role-specific approval inbox and event delivery are not implemented.
- Converted company settings into an independent scrollable dialog and bounded agent catalog and
  assignment lists so remaining definitions/rows can be reached. Added Gamma as a visibly disabled,
  planned provider slot only; no Gamma API request, secret handling, or routing is enabled.
- Localized the app shell and key dialogs to Arabic/English and applied document `lang`/`dir`, with
  theme token overrides for dark mode. Complete localization of every administration form, status,
  accessibility label and dynamic error is still open and must not be represented as finished.
- The F10 isolated restore drill and production encrypted backup/retention/RPO/RTO work are recorded
  under the final deferred work register in `MASTER_IMPLEMENTATION_PLAN.md`; they are not performed
  during this UI increment.
- Initial verification: TypeScript `tsc --noEmit --incremental false` passes. The repository's
  ESLint configuration intentionally matches only `*.mjs`, so it does not lint `page.tsx`; `git
  diff --check` passes. Responsive visual and accessibility tests remain to be run.
