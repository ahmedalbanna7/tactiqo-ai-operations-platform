# Organization, agent, tool, and data-access architecture

## Decision

Tactiqo is a multi-tenant SaaS. Every request is authorized through this
hierarchy before an agent, tool, SQL row, vector chunk, citation, or source
preview becomes visible:

```text
Organization
  -> Department
    -> Team (optional)
      -> Project / operational domain (optional)
        -> Member
```

Employees do not receive a globally privileged agent. They receive one or more
agent entitlements derived from active memberships. Every entitlement contains
an agent capability plus an immutable data/tool scope. Department membership
is mandatory; team and project memberships narrow access further and never
expand it beyond the department.

The effective permission is always the intersection of:

```text
tenant boundary
AND role grant
AND department/team/project membership
AND agent assignment
AND resource ACL and classification
AND connected-provider permissions
AND tool policy and approval policy
```

The LLM never computes or overrides this intersection. Application services
and repositories apply it before data reaches LangGraph or a model.

## Organization roles

| Role | Authority |
|---|---|
| Organization Owner | Assign organization admins and accountable owners; approve organization-wide policy |
| Organization Admin | Configure departments, teams, memberships, and approved agent catalog |
| Integration Manager | Add/rotate/revoke organization tool connections explicitly assigned by the owner |
| Department Manager | Manage members, teams, departmental agent assignments, and department-scoped sources |
| Team Manager | Manage membership and allowed agent assignments for one team only |
| Project Manager | Manage project scope and project agent access without inheriting department administration |
| Employee | Use only agents, tools, and data granted through memberships |
| Auditor / Risk Reviewer | Read scoped audit, policy, risk, and approval evidence; no implicit mutation rights |

Every privileged operation requires server-derived identity, an explicit
authorization decision, and an audit event. Organization-wide tool connections
can be created or revoked only by the assigned Integration Manager or a higher
authorized role. Provider OAuth consent does not replace Tactiqo authorization.

## Agent catalog

Agents are capability packs registered in an Agent Catalog and assigned to an
organization, department, team, or project. Assignments are deny-by-default and
can narrow tools, actions, sources, classifications, and approval requirements.

Agents are also grouped into product-facing categories. Categories explain the
agent's purpose; they never grant access. Visibility and execution rights are
configured on each agent by selecting departments, teams, projects, roles, or
specific users.

### Agent categories

| Category | Purpose |
|---|---|
| Coordination & Management | Executive, portfolio, PMO, planning, meetings, tasks, and decisions |
| Business Departments | Finance, HR, legal, sales, marketing, procurement, support, and operations |
| Industry Operations | Construction, events, facilities, quality, safety, and other installable domain packs |
| Execution & Content Studio | Email, reports, documents, spreadsheets, presentations, images, audio, and video |
| Data & Business Intelligence | Analytics, dashboards, Power BI, forecasting, KPI monitoring, and data preparation |
| Automation & Integrations | Workflow design, scheduled automation, MCP tools, system integrations, and monitoring |
| Knowledge & Research | Authorized retrieval, document analysis, citations, comparisons, and structured research |
| Safety, Risk & Governance | Risk, compliance, approvals, policy, audit, F4.1 review, fallback, and recovery |

### Planner Agent

Every non-trivial request starts with a dedicated Planner Agent before domain
agents, retrieval, or execution. The Planner produces a typed task plan; it does
not receive unrestricted data and cannot call mutation tools.

The plan defines:

```text
goal and expected deliverables
-> ordered and parallelizable steps
-> agent responsible for every step
-> data reader for every source
-> required department/team/project scope
-> required RAG collections, SQL views, and MCP tools
-> read / draft / execute / publish action level
-> risk and classification level
-> approval checkpoints
-> foreground or background execution mode
-> timeout, retry, budget, and completion criteria
```

The Policy Compiler validates each planned step against the current user's
effective entitlements. It removes or rejects unauthorized steps before any
data is retrieved. Agents receive only their assigned step and its minimum
authorized context. The plan is versioned and audited; changing tools, data
scope, assignee, or action level requires re-authorization.

Small conversational requests can use a bounded fast plan internally. Large,
multi-agent, high-risk, or externally mutating requests expose the plan in the
chat and pause at configured approval checkpoints.

### Worker Agent Runtime

Worker is the asynchronous execution runtime for long-running or resource-heavy
steps. It is not a globally visible department agent and cannot choose its own
permissions. The Planner submits a signed work envelope containing one approved
step, its agent capability, immutable scope, input references, limits, and
correlation identifiers.

Worker workloads include:

- large PDF, Word, Excel, archive, and multi-file ingestion;
- OCR, parsing, chunking, embeddings, and indexing;
- large report, spreadsheet, PowerPoint, image, audio, and video generation;
- video transcription, scene analysis, rendering, and export;
- bulk Jira/Slack reads or approved batched mutations;
- Power BI dataset preparation and scheduled refresh jobs;
- long automations, synchronization, and data-quality validation.

The Worker uses RabbitMQ queues separated by workload and risk, with bounded
concurrency, idempotency keys, leases, heartbeats, checkpoints, retries with
backoff, dead-letter queues, cancellation, and resumable progress. Large binary
inputs and outputs stay in MinIO; queue messages carry object references rather
than file content. PostgreSQL stores job state, scope, audit events, and output
metadata.

Every Worker attempt rebuilds authorization from the signed work envelope and
current policy version. Revoked membership, connection, or source access stops
the job at the next safe checkpoint. Worker output passes through malware,
content, classification, leakage, and F4.1 review before it becomes visible or
publishable.

The chat UI shows queued/running progress, current stage, estimated units rather
than false time promises, cancel/retry controls, approval waits, and final
artifacts. Users can leave the chat and return without losing the job.

| Agent | Typical owner / department | Core capabilities |
|---|---|---|
| Planner Agent | Orchestration control plane | Typed task decomposition, agent/data/tool assignment, risk and execution-mode planning |
| Worker Agent Runtime | Background execution control plane | Durable execution of approved heavy steps with progress, retry, cancellation, and artifacts |
| Executive & Strategy | Executive office | Portfolio summaries, objectives, decisions, cross-department views explicitly granted |
| PMO & Project Management | PMO | Plans, milestones, dependencies, status, Jira boards, portfolio reporting |
| Construction Operations | Construction / Engineering | Packages, drawings, RFIs, inspections, progress, contractors, site evidence |
| Events Operations | Events | Run sheets, venues, suppliers, staffing, schedules, incidents, event readiness |
| Risk & Compliance | Risk / Compliance | Risk register, controls, mitigations, compliance evidence, approval review |
| Product & Software Development | Product / Engineering | Backlogs, releases, defects, repositories, delivery metrics, engineering docs |
| Automation & Integrations | Automation / Digital Transformation | Workflow design, MCP integrations, automation health, controlled execution |
| Finance | Finance | Budgets, forecasts, costs, variance, invoices, financial evidence |
| IT Operations | IT | Incidents, assets, service requests, SLA, change management |
| People & HR | HR | Policies, hiring, onboarding, workforce operations under restricted classification |
| Procurement & Vendors | Procurement | Purchase requests, bids, contracts, suppliers, delivery and payment status |
| Legal | Legal | Contracts, obligations, legal review, restricted evidence |
| Sales & CRM | Sales | Pipeline, opportunities, accounts, forecasts, approved communications |
| Marketing | Marketing | Campaigns, content operations, performance, calendars, brand evidence |
| Customer Support & Success | Support / Customer Success | Tickets, customer health, escalations, SLA and follow-up actions |
| Operations & Facilities | Operations | Sites, facilities, resources, maintenance and operational readiness |
| Quality & HSE | Quality / Safety | NCRs, audits, inspections, incidents, corrective actions, safety evidence |
| Knowledge & Documents | Scoped per department | Retrieval, comparison, summarization, citations, source previews |
| Communications | Scoped per department | Slack search, summaries, draft messages, approval-gated sends |
| F4.1 Review, Safety & Recovery | Independent control plane | Guardrails, fallback, citation validation, injection detection, audit and recovery |

### Execution and content agents

| Agent | Outputs and actions | Default control |
|---|---|---|
| Email Execution Agent | Draft, reply, schedule, and send email; attachments and follow-up tracking | Draft allowed; external send approval-gated |
| Report Builder Agent | Operational, executive, financial, risk, and project reports with citations | Export allowed within data scope |
| Power BI & Analytics Agent | Dataset preparation, semantic-model proposals, measures, dashboards, refresh and insight summaries | Publish/share requires BI-owner approval |
| Automation Builder Agent | Design and run workflows, triggers, schedules, mappings, retries, and monitoring | Test environment first; activation approval-gated |
| Image & Design Agent | Diagrams, branded graphics, campaign images, site visuals, and controlled edits | Brand policy and external-publish approval |
| Presentation Agent | PowerPoint decks, executive briefings, project reviews, and speaker notes | Source citations required for factual claims |
| Video Production Agent | Storyboards, scripts, captions, generated clips, edits, and rendering workflows | Generation quotas and publication approval |
| Document Production Agent | Word/PDF proposals, procedures, contracts, minutes, and formatted deliverables | Templates, classification, and legal controls |
| Spreadsheet Agent | Excel models, formulas, reconciliations, analysis, charts, and imports/exports | Financial writes and external export approval |
| Meeting & Calendar Agent | Agendas, invitations, scheduling, minutes, decisions, and action items | External invitation approval configurable |
| Data Operations Agent | Data cleanup, mapping, imports, exports, validation, and controlled synchronization | Preview/dry-run before mutation |
| Social & Campaign Agent | Draft and schedule approved social or campaign content across connected tools | Brand and communications approval required |

Execution agents use the same Agent Catalog contract as departmental agents.
They are reusable capabilities, not globally available assistants. For example,
Finance may receive Report Builder and Spreadsheet agents over finance-only
data, while Marketing receives Image, Video, and Presentation agents over
marketing-only sources.

### Per-agent access configuration

The Agent Settings screen uses an agent-first assignment model:

```text
Agent
  -> category and description
  -> visible to departments
  -> visible to teams/projects
  -> role and user exceptions
  -> readable data domains and classifications
  -> allowed MCP connections and individual tools
  -> allowed actions: view / draft / execute / publish / administer
  -> approval chain by action and risk
  -> output formats, templates, quotas, and spending limits
```

`visible`, `usable`, and `executable` are separate permissions. A user can see
an agent and create a draft without receiving permission to send, publish,
share, activate an automation, modify a dashboard, or overwrite a source file.

The effective agent card shown in chat includes its category, permitted output
types, connected tools, and whether the current user has draft-only or execution
access. Hidden agents and hidden department names are never returned to the
client.

Organizations may add domain packs later without changing orchestration. An
unknown future department uses a configurable Department Operations Agent until
a specialized capability pack is installed.

## LangGraph authorization path

```text
authenticate
 -> resolve organization memberships
 -> resolve department/team/project scope
 -> resolve permitted agent assignments
 -> classify intent
 -> Planner creates typed task plan
 -> compile and authorize every plan step
 -> select only entitled agents and data readers
 -> route heavy steps to Worker queues
 -> retrieve/call with mandatory filters
 -> post-filter returned content
 -> F4.1 review
 -> approval gate for mutations/high-risk disclosure
 -> response with citations and audit references
```

If no entitled agent can satisfy the request, the run stops with a generic
access-denied response that does not reveal hidden departments, projects,
sources, documents, tools, or record counts.

## Data, RAG, SQL, and source enforcement

Every controlled resource and RAG chunk carries organization id, department
ids, optional team/project ids, classification, allowed principals, source ACL
version, and policy version. These predicates are compiled into SQL/vector
queries before retrieval. Post-filtering is defense in depth, never the primary
authorization mechanism.

Provider results from Jira, Slack, and future MCP servers are untrusted input.
The platform applies the effective internal scope after provider ACLs, redacts
disallowed fields, scans for prompt injection, and prevents returned content
from selecting tools or changing policy.

## Administration UI

The chat remains the default employee experience. A new **Company Settings**
area is visible only when the server returns an administrative entitlement.

Navigation:

```text
Company Settings
  Overview
  People & roles
  Departments
    Department manager
    Members
    Teams
    Assigned agents
    Data/source scope
  Teams
    Team manager
    Members
    Assigned agents
    Projects
  Agents
    Categories
    Catalog
    Agent details
      Visible departments / teams / projects
      User and role exceptions
      Data scope and classification
      Tools and actions
      Approval chain
      Templates, quotas, and cost limits
    Assignments
  Plans & background jobs
    Task plans and assigned agents
    Data readers and source scopes
    Running / waiting / completed / failed jobs
    Progress, cancel, retry, and approval checkpoints
    Tool/action limits
    Approval policy
  Tools & integrations
    Jira / Slack / future MCP
    Assigned integration manager
    Allowed departments and teams
    OAuth status, scopes, health, rotation, revoke
  Data & RAG access
    Sources
    Classification
    ACL inheritance
    preview-as-user test
  Policies & approvals
  Audit & security
```

The tool-add button is rendered only for the owner-assigned Integration Manager.
The backend repeats the authorization check; hiding the button is not a security
control. Department/team managers see only their delegated subtree. The UI must
include a **preview as user** policy simulator that explains allowed agents and
sources without exposing content.

## Required persistence model

```text
organization_members
organization_role_assignments
departments
department_memberships
teams
team_memberships
projects
project_memberships
agent_catalog
agent_assignments
agent_tool_grants
integration_manager_assignments
integration_scope_grants
resource_acl
data_classifications
policy_versions
authorization_decisions
```

All organization-owned tables include `organization_id`; memberships and grants
have validity intervals and revocation metadata. Referential integrity prevents
cross-organization assignments. PostgreSQL row-level security is an additional
barrier, while application authorization remains mandatory.

## Delivery order

1. Production identity context and organization roles.
2. Department/team/project persistence and membership APIs.
3. Agent Catalog and assignment policy compiler.
4. Company Settings UI with server-driven navigation and permission simulator.
5. Scope organization Jira/Slack connections to departments and teams.
6. Enforce compiled scope in LangGraph and MCP discovery/calls.
7. Build ACL-aware ingestion and hybrid RAG on the same policy compiler.
8. Add F4.1 adversarial, isolation, fallback, and audit evaluations.

No RAG indexing or additional operational agent becomes production-active until
the identity and policy compiler gates are enforced end to end.
