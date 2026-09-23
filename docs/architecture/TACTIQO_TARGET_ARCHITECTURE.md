# Tactiqo target architecture

## Purpose

This document is the target architecture agreed for Tactiqo as a scalable,
multi-tenant, chat-first AI Operations SaaS. It combines organization and
department isolation, agent visibility, task planning, foreground/background
execution, MCP tools, future ACL-aware RAG, and replaceable AI providers.

The implementation follows SOLID, dependency inversion, composition over
inheritance, explicit domain boundaries, deny-by-default authorization, and
ports-and-adapters. Free-tier APIs are initial adapters, not business-logic
dependencies. Paid or self-hosted providers are added without rewriting the
free adapters or domain services.

## System context

```mermaid
flowchart LR
    USER[Employee / Manager / Owner] --> UI[Chat + Company Settings UI]
    UI --> API[Tactiqo API]
    API --> ID[Identity & Organization Context]
    API --> ORCH[LangGraph Orchestration]
    ORCH --> BANKS[AI Provider Banks]
    ORCH --> MCP[MCP Tool Gateway]
    ORCH --> RAG[Knowledge & RAG Gateway]
    ORCH --> JOBS[Background Job Gateway]
    MCP --> JIRA[Jira / Atlassian MCP]
    MCP --> SLACK[Slack MCP]
    MCP --> FUTURE[Future SaaS Tools]
    JOBS --> WORKERS[Worker Runtime]
    RAG --> PG[(PostgreSQL + pgvector)]
    RAG --> MINIO[(MinIO Objects)]
    JOBS --> MQ[(RabbitMQ)]
    BANKS --> FREE[Free-tier APIs / Local Models]
    BANKS --> PAID[Future Paid Providers]
    ORCH --> SAFE[F4.1 Safety & Review]
    SAFE --> AUDIT[(Policy + Approval + Audit)]
```

## Organizational authorization model

```mermaid
flowchart TD
    ORG[Organization / Tenant] --> DEPT[Department]
    DEPT --> TEAM[Team - optional]
    TEAM --> PROJECT[Project / Domain - optional]
    PROJECT --> MEMBER[Employee Membership]

    OWNER[Organization Owner] --> ADMIN[Organization Admin]
    OWNER --> IM[Integration Manager]
    ADMIN --> DM[Department Manager]
    DM --> TM[Team Manager]
    DM --> PM[Project Manager]

    MEMBER --> ENT[Effective Entitlements]
    ENT --> AV[Visible Agents]
    ENT --> DS[Data / RAG / SQL Scope]
    ENT --> TS[MCP Tools and Actions]
    ENT --> AP[Approval Policy]
```

Effective access is an intersection, never a union:

```text
tenant
AND role
AND department
AND optional team/project
AND explicit agent assignment
AND resource ACL/classification
AND provider permission
AND action/tool policy
```

The server derives all identity and membership fields. Clients and models cannot
submit, broaden, or override them. Hidden agents, sources, tools, departments,
and record counts are not returned to unauthorized users.

## Agent catalog and categories

```mermaid
flowchart LR
    CATALOG[Agent Catalog] --> COORD[Coordination & Management]
    CATALOG --> BUSINESS[Business Departments]
    CATALOG --> INDUSTRY[Industry Operations]
    CATALOG --> EXEC[Execution & Content Studio]
    CATALOG --> DATA[Data & Business Intelligence]
    CATALOG --> AUTO[Automation & Integrations]
    CATALOG --> KNOW[Knowledge & Research]
    CATALOG --> GOVERN[Safety, Risk & Governance]

    COORD --> PLANNER[Planner Agent]
    COORD --> EXECUTIVE[Executive & Strategy]
    COORD --> PMO[PMO & Project Management]
    BUSINESS --> FIN[Finance]
    BUSINESS --> HR[People & HR]
    BUSINESS --> IT[IT Operations]
    BUSINESS --> PROCUREMENT[Procurement & Vendors]
    BUSINESS --> LEGAL[Legal]
    BUSINESS --> SALES[Sales & CRM]
    BUSINESS --> MARKETING[Marketing]
    BUSINESS --> SUPPORT[Customer Support & Success]
    INDUSTRY --> CONSTRUCTION[Construction Operations]
    INDUSTRY --> EVENTS[Events Operations]
    INDUSTRY --> FACILITIES[Operations & Facilities]
    INDUSTRY --> HSE[Quality & HSE]
    EXEC --> EMAIL[Email Execution]
    EXEC --> REPORTS[Report Builder]
    EXEC --> DOCS[Document Production]
    EXEC --> SHEETS[Spreadsheet]
    EXEC --> SLIDES[Presentation]
    EXEC --> IMAGE[Image & Design]
    EXEC --> VIDEO[Video Production]
    EXEC --> MEETING[Meeting & Calendar]
    DATA --> POWERBI[Power BI & Analytics]
    DATA --> DATAOPS[Data Operations]
    AUTO --> AUTOMATION[Automation Builder]
    AUTO --> COMMS[Communications]
    KNOW --> KNOWLEDGE[Knowledge & Documents]
    GOVERN --> RISK[Risk & Compliance]
    GOVERN --> REVIEW[F4.1 Review, Safety & Recovery]
```

An organization can install more domain packs. A configurable Department
Operations Agent covers a new department until a specialized pack is added.

Each agent has separate `visible`, `usable`, `draft`, `execute`, `publish`, and
`administer` grants. Seeing an Email Agent can permit drafting while sending
remains approval-gated. The same separation applies to publishing Power BI,
activating automations, sending Slack/email, exporting sensitive data, and
publishing images, presentations, or video.

## Adaptive task planning and execution

```mermaid
flowchart TD
    REQ[Authorized User Request] --> CLASS[Execution Classifier]
    CLASS -->|Fast| MICRO[Bounded Micro-plan]
    CLASS -->|Standard| PLAN[Planner Agent]
    CLASS -->|Background| PLAN

    MICRO --> POLICY[Policy Compiler]
    PLAN --> TYPED[Typed Versioned Task Plan]
    TYPED --> POLICY
    POLICY -->|Denied| DENY[Safe Non-disclosing Denial]
    POLICY -->|Approved steps| ROUTER[Agent / Data Reader / Tool Router]
    ROUTER -->|Short step| FG[Foreground LangGraph Execution]
    ROUTER -->|Heavy step| ENVELOPE[Signed Work Envelope]
    ENVELOPE --> QUEUE[RabbitMQ Workload Queue]
    QUEUE --> WORKER[Worker Agent Runtime]
    FG --> REVIEW[F4.1 Review]
    WORKER --> REVIEW
    REVIEW -->|Mutation / Publish| APPROVAL[Human Approval]
    REVIEW -->|Read / Draft allowed| RESULT[Answer + Citations + Artifacts]
    APPROVAL --> EXECUTE[Approved Execution]
    EXECUTE --> VERIFY[Verify Result]
    VERIFY --> RESULT
```

### Execution classification

| Class | Typical characteristics | Runtime |
|---|---|---|
| Fast | One entitled agent, no/heavy-free input, one read tool or simple answer, target under 8 seconds | Foreground micro-plan |
| Standard | Two to five steps, several retrievals/tools, small report, target 8–30 seconds | Foreground Planner |
| Background | Large/multiple files, OCR, audio/video, bulk records, more than five steps, resumable generation or synchronization | Planner + Worker |

Classification combines deterministic limits with a bounded estimate: input
size/type, expected records, agents, tool calls, transformation type, risk,
approvals, memory, output size, and retry/checkpoint needs. A foreground task
can escalate safely to background at a checkpoint without restarting. It never
runs the same side effect twice; every step has an idempotency key.

### Typed plan contract

```text
Plan
  id, version, goal, deliverables
  steps[]
    dependency ids
    assigned agent capability
    assigned data reader
    immutable tenant/department/team/project scope
    RAG collection / SQL view / MCP tool grants
    action: read | draft | execute | publish
    risk and classification
    foreground | background
    timeout, retry, token/cost budget
    approval checkpoint
    completion evidence
```

Planner cannot call mutation tools. Any material plan change triggers policy
recompilation and re-approval.

## Worker runtime

```mermaid
flowchart LR
    PLAN[Authorized Plan Step] --> SIGN[Signed Work Envelope]
    SIGN --> Q{Queue by workload/risk}
    Q --> DOCUMENT[Document/OCR Worker]
    Q --> MEDIA[Image/Audio/Video Worker]
    Q --> ANALYTICS[Report/Spreadsheet/BI Worker]
    Q --> SYNC[Integration/Automation Worker]
    DOCUMENT --> CHECK[Checkpoint + Heartbeat]
    MEDIA --> CHECK
    ANALYTICS --> CHECK
    SYNC --> CHECK
    CHECK --> REVIEW[F4.1 Output Review]
    CHECK --> RETRY[Bounded Retry + Backoff]
    RETRY --> DLQ[Dead-letter Queue]
    REVIEW --> OBJECTS[(MinIO Artifacts)]
    REVIEW --> STATE[(PostgreSQL Job State)]
```

Queue messages contain references, not large files or secrets. Workers restore
the execution scope, compare the current policy version, re-check revoked
memberships/connections, enforce concurrency and quota limits, and stop at safe
checkpoints. The UI exposes progress stages, cancel, retry, approvals, and final
artifacts without making unreliable time promises.

## LLM Bank

The LLM Bank selects an implementation by capability and policy. Application
code depends only on `LanguageModelPort`.

```mermaid
classDiagram
    class LanguageModelPort {
      <<interface>>
      +complete(request, context) ModelResult
      +stream(request, context) AsyncIterator
      +capabilities() ModelCapabilities
    }
    class LLMRegistry {
      +register(provider)
      +resolve(requirements, policy) LanguageModelPort
    }
    class LLMRouter {
      +execute(request, context, requirements) ModelResult
    }
    class FreeApiLLMAdapter
    class LocalLLMAdapter
    class OpenAIAdapter
    class FuturePaidAdapter
    LanguageModelPort <|.. FreeApiLLMAdapter
    LanguageModelPort <|.. LocalLLMAdapter
    LanguageModelPort <|.. OpenAIAdapter
    LanguageModelPort <|.. FuturePaidAdapter
    LLMRegistry o-- LanguageModelPort
    LLMRouter --> LLMRegistry
```

Routing requirements include language, structured output, tool calling,
context length, data classification, residency, latency, availability, quality,
token budget, and monetary budget. Free-tier quotas and availability are not
guaranteed, so the Bank includes circuit breakers, rate-limit handling, health,
bounded fallback, and usage accounting. A fallback is allowed only when its
security/residency capability is equal or stronger; sensitive prompts never
fall back to an unapproved provider.

Adding OpenAI later means implementing `LanguageModelPort`, registering provider
capabilities, adding secrets to the deployment secret manager, and changing
tenant routing configuration. Existing free adapters and agents remain intact.

## Embedding Bank

RAG and ingestion depend only on `EmbeddingPort`; they never import a provider
SDK directly.

```mermaid
classDiagram
    class EmbeddingPort {
      <<interface>>
      +embed_documents(texts, context) EmbeddingBatch
      +embed_query(text, context) Vector
      +descriptor() EmbeddingDescriptor
    }
    class EmbeddingRegistry
    class EmbeddingRouter
    class FreeApiEmbeddingAdapter
    class LocalMultilingualAdapter
    class OpenAIEmbeddingAdapter
    EmbeddingPort <|.. FreeApiEmbeddingAdapter
    EmbeddingPort <|.. LocalMultilingualAdapter
    EmbeddingPort <|.. OpenAIEmbeddingAdapter
    EmbeddingRegistry o-- EmbeddingPort
    EmbeddingRouter --> EmbeddingRegistry
```

Each vector stores `provider`, `model`, `model_version`, `dimensions`,
`normalization`, `language profile`, and `embedding_space_id`. Vectors from
different spaces are never compared. Changing a model creates a new embedding
space and a versioned background re-index job; old and new indexes can run in
parallel until quality gates pass, followed by an atomic active-space switch.

The initial provider must support Arabic and English retrieval. Provider
selection considers privacy, residency, rate limit, batch size, dimensions,
cost, and measured retrieval quality rather than price alone.

## ACL-aware RAG

```mermaid
flowchart TD
    SOURCE[Upload / Jira / Slack / Future Source] --> VALIDATE[Validate + Malware Scan]
    VALIDATE --> PARSE[Parse / OCR / Transcribe]
    PARSE --> NORMALIZE[Normalize + Structure]
    NORMALIZE --> ACL[Attach Source ACL + Classification]
    ACL --> INJECTION[Prompt Injection Scan]
    INJECTION --> EMBED[Embedding Bank]
    EMBED --> INDEX[(PostgreSQL + pgvector)]
    SOURCE --> ORIGINAL[(MinIO Original)]

    QUERY[Authorized Query] --> COMPILE[Compile Mandatory ACL Predicates]
    COMPILE --> HYBRID[Vector + Lexical + Metadata Search]
    HYBRID --> RERANK[Rerank Within Allowed Set]
    RERANK --> POST[Post-filter + Injection Defense]
    POST --> CITE[Citations + Source Preview]
```

Every chunk stores tenant, department, optional team/project, classification,
allowed principals, source ACL hash/version, content hash, locator, and
embedding-space metadata. Mandatory predicates are applied in SQL/vector search
before retrieval. Provider content is untrusted data and cannot select tools,
change instructions, or broaden access.

## MCP and tool authorization

Jira, Slack, and future connections are tenant-managed OAuth/MCP adapters.
Organization Owners assign Integration Managers and scope each connection to
departments, teams, projects, agents, and individual tools. Tool discovery is
filtered before definitions reach a model. Arguments are validated before a
call; returned fields are filtered and scanned afterward. Mutations, external
communications, publishing, deletion, financial actions, and automation
activation use configurable approval chains and durable audit.

## Company Settings UI

```mermaid
flowchart TD
    SETTINGS[Company Settings] --> PEOPLE[People & Roles]
    SETTINGS --> DEPTS[Departments]
    DEPTS --> TEAMS[Teams]
    SETTINGS --> AGENTS[Agent Categories & Catalog]
    AGENTS --> DETAIL[Agent Detail]
    DETAIL --> VIS[Visible Departments / Teams / Projects]
    DETAIL --> ACTIONS[View / Draft / Execute / Publish]
    DETAIL --> DATASCOPE[Data Scope / Classification]
    DETAIL --> TOOLGRANTS[MCP Connections / Tools]
    DETAIL --> APPROVALS[Approval Chain]
    SETTINGS --> INTEGRATIONS[Tools & Integration Managers]
    SETTINGS --> RAGSET[Data & RAG Access]
    SETTINGS --> JOBUI[Plans & Background Jobs]
    SETTINGS --> AUDITUI[Policy, Audit & Security]
    SETTINGS --> PREVIEW[Preview as User]
```

The employee chat receives only entitled agent cards. The default experience
may show one Tactiqo Agent while the Supervisor delegates invisibly to entitled
specialists. Administrative navigation is server-driven. UI hiding is never an
authorization control; every API repeats the decision.

## Module boundaries

```text
identity/          users, sessions, tenants, server-derived context
organization/      departments, teams, projects, memberships, managers
authorization/     RBAC + ABAC + ReBAC policy compiler and decisions
agents/            catalog, assignments, Planner, Supervisor, domain packs
ai_providers/      LLM Bank and Embedding Bank ports/registries/adapters
integrations/      OAuth connections and provider-specific MCP adapters
tools/             discovery, policy, approvals, execution, audit
knowledge/         ingestion, ACL-aware retrieval, citations, source preview
jobs/              plans, work envelopes, queues, workers, progress, recovery
artifacts/         reports, documents, spreadsheets, BI, images, slides, media
safety/            F4.1 validation, guardrails, fallback, red-team evaluation
```

Dependencies point inward toward domain/application contracts. Provider SDKs,
FastAPI, SQLAlchemy, RabbitMQ, MinIO, model APIs, and vector implementations stay
in infrastructure adapters.

## Non-negotiable controls

- deny by default and prevent cross-tenant identifiers at database boundaries;
- never authorize from model output or browser-submitted scope;
- encrypt provider credentials and platform secrets; never log or prompt them;
- preserve source permissions and classification through ingestion and output;
- require idempotency and approval for impactful actions;
- isolate model and embedding spaces by policy and version;
- record sanitized plan, policy decision, tool call, approval, and artifact lineage;
- fail closed when identity, policy, provider capability, or ACL metadata is missing;
- test tenant, department, team, project, agent, tool, SQL, RAG, and artifact isolation.

