# Target System Hierarchy

Status: proposed target architecture baseline for review. This document defines
boundaries and dependency direction; it does not approve the open agent, RAG,
broker, provider, or cloud topology decisions listed in
`docs/decisions/OPEN_DECISIONS.md`.

## 1. Governance hierarchy

```text
Security, privacy, isolation, and human approval
  -> Explicit human decisions and approved ADRs
    -> Engineering Constitution
      -> Master Product Specification
        -> Phase plan
          -> Epic / story / task
```

Any lower level must comply with every higher level. Exceptions require an ADR
and explicit human approval.

## 2. Product capability hierarchy

```text
Tactiqo Enterprise Deployment
  |-- Identity, Authentication, and Access
  |-- Organization Hierarchy and Company Setup
  |-- Industry and Domain Configuration
  |-- Projects, Portfolios, Delivery, and Operations
  |-- Quality, Readiness, Acceptance, and Handover
  |-- Risk and RAID
  |-- Connectors and Ingestion
  |-- Knowledge, Search, and RAG
  |-- Chat and Governed Agent Orchestration
  |-- Human Approvals and External Actions
  |-- Reports and Notifications
  |-- Audit, Governance, Evaluation, and Observability
```

These are modules inside the initial modular monolith. A module becomes an
independently deployed service only after an approved ADR demonstrates a need
for independent scale, isolation, ownership, failure handling, deployment
cadence, or specialized compute.

## 3. Runtime component hierarchy

```text
User / OIDC Identity Provider
  -> Next.js Web Application
    -> FastAPI API
      -> Authentication and server-derived AccessContext
      -> Deterministic DomainContextResolver
      -> Application use case
        -> Domain policy / aggregate
        -> Internal port
          -> PostgreSQL / Redis / RabbitMQ / MinIO adapter
          -> KnowledgeSearchPort -> authenticated Onyx API -> Vespa
          -> ModelProviderPort -> approved OpenAI adapter
          -> Connector port -> selected external system
      -> Audit, metrics, traces, and safe response

RabbitMQ command/job
  -> Bounded worker
    -> Revalidate signed execution scope
    -> Application use case
    -> Transaction + transactional outbox
    -> Idempotent outbox consumer

Uploaded or synchronized file
  -> Object storage
  -> RabbitMQ parsing job
  -> isolated DocumentParser / Unstructured worker
  -> canonical elements + provenance + ACL metadata
  -> candidate validation and/or KnowledgeSearchPort indexing
```

No API route, worker, agent node, connector, parser, or provider adapter owns
business truth. PostgreSQL owns official transactional records. Object storage
owns original file bytes. Onyx/Vespa is a rebuildable derived search index.

## 4. Backend dependency hierarchy

Every domain module follows this direction:

```text
Presentation / Transport
  -> Application use cases
    -> Domain entities, value objects, services, and policies
      -> Ports / protocols
        <- Infrastructure adapters
```

Rules:

- Presentation maps HTTP, SSE, webhook, or job messages to typed application
  commands and queries.
- Application coordinates transactions, authorization, ports, and domain
  behavior.
- Domain code contains invariants and deterministic policy. It has no FastAPI,
  ORM, broker, cache, cloud, search, or model dependency.
- Ports are focused contracts such as repositories, `KnowledgeSearchPort`,
  `DocumentParser`, `ModelProvider`, `ObjectStorage`, and connector readers or
  writers.
- Infrastructure implements ports and maps vendor payloads to canonical models.
- Cross-module work uses public application interfaces or versioned domain
  events. One module must not import another module's internal repository or
  tables directly.

## 5. Organizational and access hierarchy

```text
Dedicated enterprise deployment
  -> Organization / group
    -> Legal entity or subsidiary
      -> Division / sector
        -> Business unit
          -> Department
            -> Section
              -> Team / committee / temporary unit
```

The tree is versioned. Adjacency is the source of truth and PostgreSQL `ltree`
or a closure table is the read optimization selected by an ADR. Departments are
not workspaces.

People and authority are modeled separately:

```text
Person/User
  -> active Position Assignment(s)
    -> Position
      -> Organizational Unit
      -> primary or dotted Reporting Relationship
      -> time-limited Management Delegation
```

Effective access is calculated server-side:

```text
eligible hierarchy/project scope
AND role permission
AND resource policy
AND synchronized source ACL
AND classification clearance
AND explicit grants
MINUS explicit denies
```

Explicit deny wins. A client-provided organization unit, project, or scope is a
filter only and never an authorization grant.

## 6. Configuration inheritance hierarchy

```text
Organization Industry Profile
  -> Organizational Unit Activity Profile
    -> Project Industry Profile
      -> immutable, versioned Compiled DomainContext
```

Configuration changes follow draft, preview, validation, approval, activation,
audit, cache invalidation, and rollback. Normal chat reads an active compiled
`DomainContext`; it never asks an LLM to rediscover industry or department
activity.

## 7. Data truth hierarchy

```text
Original external/file evidence
  -> immutable source reference and version
  -> canonical normalized object or document element
  -> extracted operational/configuration candidate
  -> deterministic validation
  -> assigned human validation task
  -> approval policy satisfied
  -> official versioned platform record
```

The platform preserves the distinction among source-reported facts,
deterministic calculations, AI inference, human-approved records, and executed
external actions.

## 8. Retrieval and response hierarchy

```text
Authenticate
  -> calculate AccessContext
  -> resolve active DomainContext
  -> authorize request and tools
  -> apply organization/project/ACL/classification/time filters
  -> retrieve structured and/or knowledge candidates
  -> fuse/deduplicate; rerank only if approved profile enables it
  -> revalidate access and freshness
  -> construct minimum authorized context
  -> generate grounded answer
  -> validate citations, trust level, and policy
  -> return response or proposed action
```

Permissions are enforced before retrieval and again before context/citation
delivery. Vector similarity is never authorization.

## 9. Human approval hierarchy

```text
Read-only analysis
  -> Draft
    -> Proposed material change/action
      -> deterministic policy and approver resolution
        -> one/group/sequential/parallel/four-eyes approvals
          -> freshness and permission revalidation
            -> idempotent execution
              -> external-result reconciliation and immutable audit
```

AI can recommend an approver but cannot define the permitted approver set,
self-approve, or bypass separation-of-duties policy.

## 10. Deployment hierarchy

```text
Local Docker Compose
  |-- core: web, API, worker, PostgreSQL, Redis, RabbitMQ, MinIO
  |-- knowledge: Onyx, Vespa, Unstructured/OCR workers
  `-- observability: OpenTelemetry collector and approved local dashboards

Shared development/staging
  -> Kubernetes-capable application images
    -> customer-specific AWS or Azure deployment profile
```

The same stateless application images should move between environments through
configuration and adapters. Terraform, Helm/Kubernetes resources, cloud-managed
replacements, and DR targets are added only after the deployment target is
approved.

## 11. Initial module ownership

| Module | Owns | Must not own |
|---|---|---|
| `identity` | users, identities, roles, permissions | organization tree |
| `organization` | units, hierarchy versions, positions, assignments, reporting, delegations, access context | source connector ACL truth |
| `company_setup` | setup state, import sessions, candidates, validation tasks, activation batches | automatic activation |
| `industries` | packs, profiles, inheritance, compiled DomainContext | runtime industry inference |
| `projects` | portfolios, programs, projects, memberships, core work objects | vendor payload models |
| `operations` | actions, handoffs, SLAs, coordination | approval policy |
| `delivery` | baselines, snapshots, deterministic health/forecast components | opaque employee scoring |
| `quality` | requirements, evidence, gates, readiness, acceptance | silent overrides |
| `risks` | RAID records, scoring, mitigation lifecycle | unapproved AI risks as official records |
| `connectors` | connector contracts, installations, cursors, source ACL sync | business canonical policy |
| `ingestion` | jobs, normalization workflow, raw/source processing | official approval decisions |
| `knowledge` | documents, versions, canonical elements/chunks, provenance | organization authorization source |
| `search` | retrieval contracts, profiles, result normalization | business truth or direct Vespa access |
| `chat` | conversations, SSE response lifecycle | durable organizational memory by accident |
| `agents` | bounded orchestration, typed tools/state, checkpoints | permissions, official truth, provider internals |
| `approvals` | policies, proposals, decisions, execution lifecycle | self-approval |
| `reports` | report definitions, generation, versions | external distribution without approval |
| `notifications` | preferences, routing, drafts, delivery status | uncontrolled sending |
| `audit` | append-only evidence of security and material events | mutable business state |
| `evaluation` | test cases, runs, quality/cost regression gates | production policy decisions |

## 12. Boundary verification

Architecture tests will enforce allowed imports. Contract tests will enforce
provider, connector, parser, storage, and search behavior. Security tests will
prove organization, hierarchy, project, delegation, classification, and source
ACL isolation.
