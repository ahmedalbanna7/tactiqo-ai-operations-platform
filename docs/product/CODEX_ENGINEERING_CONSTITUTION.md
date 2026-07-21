# Codex Engineering Constitution

## Mandatory Architecture, Code Quality, Scalability, AI, RAG, and Delivery Rules

**Document status:** Consolidated engineering baseline — approved decisions plus explicit review gates
**Applies to:** All code, infrastructure, tests, migrations, agents, RAG pipelines, connectors, and documentation created for the AI Operations Platform
**Relationship to product specification:** This document defines **how Codex must build**. `AI_OPERATIONS_PLATFORM_MASTER_SPEC.md` defines **what the product must do**.

---

## 1. Purpose

This document is the engineering constitution for Codex and all developers working on the platform. Its rules are mandatory unless an approved Architecture Decision Record (ADR) explicitly creates an exception.

The platform must be:

- Scalable for high traffic and large enterprise datasets
- Secure and permission-aware
- Maintainable and easy to extend
- Observable and testable
- Resilient to external-service and AI-provider failures
- Modular without unnecessary distributed-system complexity
- Built with clean code, OOP, SOLID principles, and appropriate design patterns
- Designed for durable agentic workflows and enterprise-grade RAG
- Deployable on AWS or Azure

Codex must not silently change these rules. If a rule is unsuitable for a specific task, Codex must explain the conflict, present alternatives and tradeoffs, and request approval before recording an exception.

---

## 2. Rule Language

- **MUST / MUST NOT:** Mandatory.
- **SHOULD / SHOULD NOT:** Expected unless Codex documents a justified exception.
- **MAY:** Optional.
- **APPROVAL REQUIRED:** Codex must stop at the decision point, present options, and wait for human approval before implementation.

Priority when documents conflict:

1. Security, privacy, data isolation, and human-approval requirements
2. Approved ADRs and explicit human decisions
3. This Engineering Constitution
4. Master Product Specification
5. Individual story/task notes

---

## 3. Core Engineering Principles

1. **Correctness before cleverness.** Prefer explicit, understandable code.
2. **Security by design.** Authorization happens before data access and model context construction.
3. **Human-in-the-loop before impact.** Agents propose; authorized humans decide and approve material actions.
4. **Deterministic core, probabilistic edge.** Permissions, calculations, policies, approvals, workflow state, and data integrity use deterministic code.
5. **Modular architecture.** Business domains have clear boundaries and contracts.
6. **Async by design where justified.** Slow, bursty, retryable, or high-volume work must not block API requests.
7. **Idempotency everywhere it matters.** Repeated messages/jobs/actions must not create duplicate effects.
8. **Observability is part of the feature.** A workflow is incomplete without logs, metrics, traces, and failure visibility.
9. **Design for change.** External connectors, LLMs, embedding models, vector stores, and cloud services stay behind interfaces.
10. **Evidence over assumptions.** Performance and architecture changes must use measurements, load tests, and production telemetry.
11. **No premature distribution.** Begin with a well-structured modular system; extract deployable services only where scaling, isolation, ownership, or reliability requires it.
12. **No premature AI.** Do not use an LLM where validation rules, SQL, search, parsing, or ordinary algorithms solve the problem reliably.

---

## 4. Approved Technology Direction

### 4.1 Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x async
- Alembic
- PostgreSQL 16+
- Redis
- Apache Kafka-ready domain-event contracts and outbox; deploy Kafka only after an approved scale/use-case trigger
- RabbitMQ
- Celery or a comparable RabbitMQ-compatible worker framework for command/job processing
- LangChain and LangGraph for approved AI/RAG/agent workflows
- Object storage abstraction supporting S3, Azure Blob Storage, and MinIO locally
- OpenTelemetry
- pytest ecosystem

### 4.2 Frontend

- Next.js
- React
- TypeScript with strict mode
- Tailwind CSS
- A consistent accessible component/design system
- TanStack Query
- Zod
- React Hook Form
- SSE for normal token/progress streaming; WebSocket only when genuine bidirectional real-time behavior requires it

### 4.3 Infrastructure

- Docker for local and production images
- Docker Compose for local development
- Terraform for AWS/Azure infrastructure
- GitHub Actions or the customer-approved CI/CD platform
- AWS ECS/EKS or Azure Container Apps/AKS according to deployment requirements
- Managed PostgreSQL, Redis, Kafka, RabbitMQ/message broker, object storage, secrets, monitoring, and key management where appropriate

Technology versions must be pinned through dependency files and updated through reviewed changes with tests.

### 4.4 Full target architecture, phased implementation

The complete platform architecture MUST be designed before implementation begins. Phased delivery does not mean designing only a small MVP that cannot grow into the full system.

Codex MUST distinguish:

- **Target architecture:** the complete intended system, boundaries, data flows, security, RAG, agents, messaging, storage, provider abstractions, scaling, observability, and deployment model.
- **Implementation phases:** safe, testable increments that progressively realize the target architecture.

Every phase MUST preserve the agreed target boundaries and extension points. Temporary implementations MUST be labelled, isolated behind interfaces, and have a replacement/migration path. Codex MUST NOT hard-code a Phase 1 provider or database in a way that prevents later options.

### 4.5 Pluggable AI and data-provider law

Every replaceable AI/data capability MUST use a stable internal interface, provider adapter, provider registry, capability metadata, and versioned configuration profile.

Pluggable capability categories:

- Chat/reasoning LLM
- Fast/low-cost LLM
- Structured-output LLM
- Vision/multimodal model
- Embedding model
- Reranking model
- Vector database
- Full-text/hybrid search engine
- OCR/document-intelligence provider
- Document parser
- Speech-to-text/text-to-speech if added
- Safety/moderation provider
- Agent checkpoint store

Business/application code MUST depend on internal capability interfaces, never directly on an OpenAI, Azure, AWS, Anthropic, Google, Cohere, Qdrant, Pinecone, Weaviate, or other vendor SDK.

Required provider architecture:

```text
Business Use Case / Agent / RAG Pipeline
                ↓
       Internal Capability Interface
                ↓
     Provider Router and Policy Engine
                ↓
       Provider Adapter Registry
                ↓
 OpenAI / Azure / Bedrock / Anthropic / Gemini / Local / etc.
```

Each provider adapter MUST declare capabilities such as:

- Supported model types
- Streaming
- Tool/function calling
- Structured output/JSON schema
- Vision/audio support
- Context limits
- Embedding dimension
- Batch support
- Data residency/region
- Rate limits and concurrency limits
- Cost metadata
- Timeout/retry behavior
- Provider-specific safety constraints

Unsupported capabilities MUST fail during configuration validation, not during a production user request.

### 4.6 Simple AI Provider Settings

The initial product MUST expose a simple AI settings page for Owner/Super Admin. It is not a large provider-management platform in the first release.

Initial settings:

- OpenAI API key/secret reference
- Main chat/reasoning model name
- Fast/low-cost model name if different
- Structured extraction model name if different
- Embedding model name
- Optional OpenAI-compatible base endpoint for development/testing
- Timeout and retry policy
- Basic rate/concurrency and token/cost limits
- Connection-test status
- Activation version and approval history

The code still uses simple logical profiles:

- `default_reasoning_llm`
- `fast_chat_llm`
- `structured_extraction_llm`
- `vision_document_llm`
- `default_embedding_model`
- `multilingual_embedding_model`
- `primary_vector_store`
- `hybrid_search_profile`

Initial profiles are enterprise-wide unless a real requirement justifies department/project overrides. Advanced provider routing, multiple fallbacks, regional routing, and complex per-department profiles are future capabilities—not Phase 1 requirements.

### 4.7 Credentials and secret keys

Users MUST be able to configure an API key, cloud credential reference, managed identity, or endpoint credential for approved providers, but secrets MUST NOT be stored or returned as ordinary application data.

Rules:

- AWS deployments use AWS Secrets Manager/KMS and IAM roles where possible.
- Azure deployments use Azure Key Vault and Managed Identity where possible.
- The application database stores only a `secret_reference`, provider metadata, owner/scope, and last-rotation/status information.
- Secret values are write-only in the UI and masked after saving.
- Secret values MUST NOT appear in API responses, logs, traces, prompts, events, exceptions, or audit payloads.
- A secure server-side connection test validates credentials and capabilities before activation.
- Creating, changing, or rotating a production provider credential requires authorization, audit, and configured human approval.
- Credentials are scoped to the minimum permissions and may be limited by department/use case.
- Rotation MUST not require code changes or redeployment.
- Fallback providers MUST have separately approved credentials and privacy/data-residency compatibility.

### 4.8 Future adapter catalogue—not initial implementation

The interfaces and registry SHOULD make it possible to add the following options later without rewriting business/RAG/agent code. Codex MUST NOT implement these adapters until a real customer, deployment, evaluation, or approved roadmap item requires them.

**LLM providers:**

- OpenAI
- Azure OpenAI
- AWS Bedrock
- Anthropic
- Google Gemini/Vertex AI
- OpenAI-compatible endpoints
- Local/self-hosted models through vLLM or another approved serving layer

**Embedding providers:**

- OpenAI/Azure OpenAI embeddings
- AWS Bedrock embeddings
- Google/Vertex embeddings
- Cohere embeddings
- Hugging Face/Sentence Transformers
- Local/self-hosted embedding endpoints

**Rerankers:**

- Cohere Rerank
- Cross-encoder models
- BGE rerankers
- Managed cloud reranking where available

**Vector/search stores:**

- PostgreSQL + pgvector
- Qdrant
- Weaviate
- Milvus/Zilliz
- Pinecone if approved
- OpenSearch
- Azure AI Search
- Other provider adapters after contract tests

The future catalogue is documentation of expansion paths, not a Phase 1 backlog. Initially implement only the approved baseline in section 4.10.

### 4.9 Provider switching and migration

Switching providers MUST be controlled and versioned.

For LLMs:

- Run compatibility and regression evaluations.
- Validate tool calling, structured output, context limits, safety, latency, and cost.
- Support controlled canary/shadow evaluation where permitted.

For embedding models:

- Embedding records MUST store provider, model, version, dimension, normalization, and index version.
- Different embedding spaces MUST never be mixed in the same logical index version.
- Model changes require a new index version and resumable re-embedding/reindexing.
- Old and new indexes may run in parallel until evaluation and human activation.

For vector stores:

- Use an internal `VectorStore` contract and canonical chunk identifiers/metadata.
- Support export/reindex from the canonical document/chunk store rather than treating the vector database as the only data copy.
- Migration uses dual-indexing or controlled rebuild, evaluation, cutover, and rollback.

Provider activation and rollback MUST NOT require changing application business code.

### 4.10 Approved simple initial AI and retrieval baseline

The following initial providers are approved for implementation. They define the first production adapters and default profiles, but all application code MUST continue to use the provider interfaces, router, registry, and versioned profiles.

| Capability | Initial implementation | Future expansion path | Initial profile |
|---|---|---|---|
| LLM | OpenAI only | Azure OpenAI/Bedrock/other adapters later | `default_reasoning_llm`, `fast_chat_llm`, `structured_extraction_llm` |
| Embeddings | OpenAI Embeddings only | Azure/local/other adapters later | `default_embedding_model`, `multilingual_embedding_model` |
| Knowledge/RAG engine | Onyx Community Edition/Standard with its Vespa index | Azure AI Search/OpenSearch/custom pgvector adapter later | `primary_knowledge_search`, `hybrid_search_profile` |
| Document parsing | Unstructured OSS workers | Azure Document Intelligence/AWS or other adapters later | `primary_document_parser` |
| Agent orchestration | LangChain + LangGraph | Additional approved workflow/runtime adapters only if justified | `primary_agent_runtime` |
| Reranker | No mandatory reranker initially; add BGE local when evaluation shows need | Cohere/managed alternatives later | `default_reranker` when enabled |

Implementation requirements:

- Implement one production OpenAI LLM adapter satisfying the internal LLM contract.
- Implement one production OpenAI embedding adapter satisfying the internal embedding contract.
- Integrate Onyx only through an authenticated `KnowledgeSearchPort`; business and agent code must not depend on Onyx/Vespa internals.
- Use Onyx-owned Vespa as the single initial knowledge vector/keyword index; do not operate a duplicate pgvector index without an approved distinct use case.
- Implement Unstructured OSS behind the `DocumentParser` contract in isolated workers and normalize every result to canonical platform elements.
- Use LangGraph for approved stateful/checkpointed/HITL workflows; keep deterministic business services outside graph internals.
- Keep a `Reranker` interface and no-op/pass-through implementation; add BGE only after retrieval evaluation shows reranking is required.
- Do not import provider SDKs outside their infrastructure adapter packages.
- Contract tests MUST run against every implemented adapter.

The initial Provider Resolver MUST enforce:

- Customer deployment policy
- Data residency and privacy rules
- Department/project classification
- Model capability requirements
- Health and rate-limit status
- Approved cost/latency policy
- No automatic cross-provider fallback

If OpenAI is unavailable, the system enters a clear degraded state or retries according to policy. It does not require another provider in the initial release.

The initial Onyx/Vespa knowledge design MUST remain behind `KnowledgeSearchPort` so Azure AI Search, OpenSearch, pgvector, or another engine can be added later without changing agent or business code.

Changing the OpenAI embedding model—or adding another provider later—requires compatibility validation. If the embedding space is not proven identical, create a new embedding/index version, re-embed, evaluate, approve, and cut over safely.

### 4.11 Simple low-cost/open-source initial platform

Except for the chosen OpenAI API usage and required cloud hosting, the initial development stack SHOULD prefer simple, widely supported open-source components with no additional SaaS subscription.

Initial stack:

| Capability | Initial choice |
|---|---|
| Transactional database | PostgreSQL |
| Enterprise knowledge/search | Onyx Community Edition/Standard |
| Vector + keyword index | Vespa owned internally by Onyx |
| Cache/rate limits | Redis |
| Background jobs | RabbitMQ + approved Python worker framework |
| Local object storage | MinIO |
| Cloud object storage | S3-compatible or Azure Blob adapter when deployed |
| Document/PDF parsing | Unstructured OSS primary adapter; native fallbacks only where justified |
| OCR | Tesseract initially; managed document intelligence only after justified approval |
| Reranking | None initially; BGE local after evaluation if required |
| Agent workflows | LangChain + LangGraph |
| Telemetry standard | OpenTelemetry |
| Local metrics/tracing dashboards | Prometheus/Grafana/Jaeger or a smaller approved open-source subset |
| Local orchestration | Docker Compose |

Rules:

- Do not introduce a paid SaaS dependency when the initial requirement is met reliably by the approved local/open-source component.
- Cloud-managed equivalents MAY replace operations-heavy components for production after cost/operations review; adapters and configuration must preserve portability.
- Do not run a component merely because it appears in the target architecture. Every running service must have a current use case, owner, health check, backup/recovery decision, and monitoring.
- Prefer one reliable database/search path initially over operating multiple overlapping databases.
- Expansion points are interfaces and contracts, not inactive production infrastructure.
- Onyx, LangGraph, and Unstructured versions MUST be pinned and upgraded through compatibility tests and reviewed release notes.

### 4.12 Local-first and cloud/Kubernetes-ready law

Initial development MUST run on a developer machine through Docker Compose without requiring an AWS/Azure account or paid managed infrastructure. This constraint must not create local-only application code.

Initial local profiles:

- `core`: platform API, web, PostgreSQL, Redis, RabbitMQ, MinIO
- `knowledge`: Onyx Community Edition/Standard, Vespa, Unstructured parsing workers, and required inference/OCR dependencies
- `observability`: optional local OpenTelemetry collector and approved dashboards

Rules:

- Images, ports, volumes, networks, health checks, resource expectations, and startup dependencies are documented.
- Stateful services use persistent volumes locally; backup/restore and clean-reset commands are documented.
- Application/worker containers are stateless apart from bounded temporary files.
- No business code depends on Docker hostnames, local filesystem paths, or a specific cloud SDK.
- Object storage, secrets, model providers, knowledge search, queues, caches, and OCR use internal ports/adapters.
- Kubernetes is not required for early local development.
- Kubernetes manifests/Helm and Terraform are added when the first deployment target is known.
- The same application images SHOULD run locally and in Kubernetes with configuration differences only.

Future AWS/Azure mapping:

| Port/capability | Local | AWS option | Azure option |
|---|---|---|---|
| Object storage | MinIO | S3 | Blob Storage |
| PostgreSQL | Container | RDS PostgreSQL | Azure Database for PostgreSQL |
| Redis | Container | ElastiCache | Azure managed Redis option |
| Job queue | RabbitMQ container | Amazon MQ/approved adapter | RabbitMQ on AKS or approved queue adapter |
| Knowledge search | Onyx/Vespa containers | Onyx/Vespa on EKS or future OpenSearch adapter | Onyx/Vespa on AKS or future Azure AI Search adapter |
| LLM/embeddings | OpenAI | OpenAI/Bedrock later | OpenAI/Azure OpenAI later |
| Document parsing | Unstructured/Tesseract | Same on EKS or AWS adapter later | Same on AKS or Azure Document Intelligence later |
| Secrets | Local dev secret file only | Secrets Manager/KMS | Key Vault/Managed Identity |

Managed cloud replacements are optional future decisions. Maintainability comes from ports, canonical models, versioned contracts, rebuildable indexes, and migration tests—not from implementing every provider now.

---

## 5. Architecture Law

### 5.1 Starting architecture

The initial architecture MUST be a **modular monolith with independent asynchronous workers**, not an unstructured monolith and not dozens of premature microservices.

Required domain boundaries include:

- Identity and authentication
- Organization hierarchy and access control
- Company setup and configuration
- Industry/domain configuration
- Projects and portfolios
- Operations and delivery
- Quality and readiness
- Risk and RAID
- Connectors and ingestion
- Knowledge and RAG
- Search
- Chat and conversations
- Agent orchestration
- Human approvals and actions
- Notifications and reports
- Audit and governance
- Observability and evaluation

Each module MUST own its domain logic. Cross-module access MUST use public application interfaces or domain events, not direct imports into internal repositories or tables without an approved design.

### 5.2 Layering

Backend modules SHOULD use clear layers:

```text
API / Transport
    ↓
Application Use Cases
    ↓
Domain Model and Policies
    ↓
Ports / Interfaces
    ↓
Infrastructure Adapters
```

Rules:

- FastAPI route handlers MUST remain thin.
- Route handlers MUST NOT contain business logic or direct SQL.
- Domain logic MUST NOT depend on FastAPI, Kafka, RabbitMQ, Redis, cloud SDKs, or a specific LLM provider.
- Infrastructure implementations depend on domain/application interfaces, not the reverse.
- External provider payloads MUST be mapped into internal canonical models at boundaries.
- Pydantic API schemas MUST NOT become database/domain models by accident.

### 5.3 Service extraction criteria

A module MAY become a separate service only when evidence shows at least one of:

- Independent scaling requirement
- Strong security or data isolation boundary
- Different failure/reliability profile
- Separate deployment cadence or ownership
- Specialized compute dependency such as OCR/GPU workloads
- Sustained workload that harms the primary application

Extraction requires an ADR covering contracts, data ownership, consistency, observability, deployment, and failure handling.

### 5.4 Architecture approval gate

Before implementing a major subsystem, Codex MUST present:

- Problem and constraints
- Proposed component diagram
- Data flow
- Module/service boundaries
- Sync versus async choices
- Storage choices
- Failure modes
- Security and authorization flow
- Scalability approach
- Alternatives and tradeoffs
- Testing and observability strategy

Agentic architecture, RAG architecture, vector database, graph database, search engine, model provider, and major service extraction are **APPROVAL REQUIRED** decisions.

---

## 6. SOLID Principles

All domain and application code MUST follow SOLID principles pragmatically.

### 6.1 Single Responsibility Principle

Each class/module/function should have one clear reason to change.

Examples:

- A parser parses; it does not store embeddings.
- A repository persists/retrieves domain data; it does not decide business policy.
- An authorization policy decides access; an API handler only invokes it.
- A connector adapter talks to the external tool; a mapper converts its data.

### 6.2 Open/Closed Principle

New connectors, document parsers, model providers, embedding providers, vector stores, notification channels, report formats, and Industry Packs SHOULD be added through interfaces and registration—not large conditional chains modifying core behavior.

### 6.3 Liskov Substitution Principle

Every interface implementation MUST honor the same behavioral contract, error semantics, and invariants. A provider adapter must not surprise callers with incompatible behavior.

### 6.4 Interface Segregation Principle

Use focused interfaces such as:

- `DocumentParser`
- `EmbeddingProvider`
- `VectorStore`
- `Reranker`
- `ConnectorReader`
- `ConnectorWriter`
- `ApprovalPolicy`
- `NotificationSender`

Do not create a single large interface that forces implementations to support unused operations.

### 6.5 Dependency Inversion Principle

High-level domain/application code MUST depend on protocols/abstract interfaces. Infrastructure adapters implement those interfaces and are injected through composition roots.

---

## 7. Object-Oriented Programming Rules

OOP MUST be used for domain entities, value objects, policies, strategies, adapters, and lifecycle-rich concepts where state and behavior belong together.

Required practices:

- Prefer composition over inheritance.
- Keep inheritance shallow and justified.
- Use Python `Protocol` or ABCs for stable contracts.
- Use immutable value objects where possible.
- Protect domain invariants inside domain methods.
- Avoid anemic objects when behavior clearly belongs to the entity/value object.
- Avoid “God classes,” manager classes with dozens of responsibilities, and hidden global state.
- Use dataclasses or Pydantic models intentionally; do not mix domain and transport concerns.
- Dependency injection occurs at application startup/composition boundaries.

Functional and procedural code MAY be used where it is clearer, especially for pure transformations. “Apply OOP” does not mean wrapping every utility in a class.

---

## 8. Required Design Patterns

Patterns MUST solve real problems; Codex MUST NOT add patterns only to appear sophisticated.

Preferred patterns by use case:

| Pattern | Use |
|---|---|
| Repository | Persistence boundary for aggregates/read models |
| Unit of Work | Transaction boundaries across repositories |
| Factory | Create connector/parser/provider from configuration |
| Strategy | Chunking, reranking, risk scoring, notification policy |
| Adapter | External APIs, cloud services, LLMs, vector stores |
| Facade | Simple application interface over complex subsystem |
| Command | Intentional write/action requests |
| Query/CQRS-lite | Separate complex reads from business writes where beneficial |
| Observer/Domain Events | React to domain changes without tight coupling |
| State Machine | Approval, setup, sync, document, and agent workflow lifecycle |
| Specification/Policy | Composable authorization and business rules |
| Chain of Responsibility | Guardrails/validation stages |
| Circuit Breaker | Unstable external providers |
| Retry | Transient failures only, with limits and idempotency |
| Outbox/Inbox | Reliable database/event integration and deduplication |
| Saga/Process Manager | Multi-step distributed workflows requiring compensation |
| Builder | Complex immutable request/context construction |

Every non-obvious pattern MUST be documented in code and, for major patterns, in an ADR.

---

## 9. Clean Code and Maintainability

### 9.1 General rules

- Use meaningful, business-oriented names.
- Functions and methods MUST be small and focused.
- Prefer early validation and guard clauses over deeply nested conditions.
- No duplicated business rules.
- No magic numbers or strings; use typed constants/enums/configuration.
- No broad `except Exception` without controlled translation, logging, and rethrow/handling.
- No mutable default arguments.
- No hidden network/database calls in property getters or domain entities.
- No synchronous blocking I/O inside async request paths.
- No raw secrets, tokens, credentials, or personal data in code/logs.
- No dead code or commented-out code in committed changes.
- No TODO without an issue/reference, owner/intent, and risk explanation.
- Public interfaces must be backward-compatible or versioned/migrated.

### 9.2 Function and method documentation

Every class, public function, private function, and method MUST have a useful docstring.

Docstrings MUST explain as applicable:

- Purpose and business meaning
- Arguments and important constraints
- Return value
- Raised domain/application exceptions
- Side effects
- Authorization expectations
- Idempotency behavior

Inline comments MUST explain **why**, assumptions, edge cases, algorithms, security rules, or non-obvious tradeoffs. They MUST NOT restate obvious code line by line.

Example:

```python
async def approve_action(
    action_id: UUID,
    approver: AccessContext,
) -> ApprovedAction:
    """Approve a proposed external action after policy and freshness checks.

    Args:
        action_id: Stable identifier of the proposed action.
        approver: Server-derived identity, hierarchy, and authorization context.

    Returns:
        The newly approved action version.

    Raises:
        ActionNotFound: When the action is unavailable in the approver's scope.
        ApprovalDenied: When policy does not allow this approver.
        StaleProposal: When source data changed after the proposal was created.

    Side Effects:
        Stores an approval event. It does not execute the external action.
    """
```

### 9.3 Size and complexity

Codex SHOULD flag and refactor:

- Large modules with unrelated responsibilities
- Functions with high cyclomatic complexity
- Classes with excessive dependencies
- Deeply nested branches
- Repeated conditionals indicating a missing strategy/policy
- Circular imports

Static analysis thresholds must be configured in CI and tightened gradually rather than bypassed.

---

## 10. Python Standards

- Full type hints are mandatory.
- Use `mypy` or `pyright` in strict/strong mode.
- Use Ruff for linting and formatting unless the project approves an alternative.
- Pydantic validates untrusted input at boundaries.
- Use timezone-aware UTC datetimes internally.
- Use UUIDs or approved non-guessable identifiers for public resources.
- Use domain-specific exception types and centralized API error translation.
- Use structured logging with correlation IDs.
- Use async only for real concurrency/I/O; do not make pure computation async.
- Limit concurrency with semaphores/pools when calling providers.
- Use context managers for resources.
- Configuration is typed, validated, environment-aware, and secret-free.
- Production code MUST NOT rely on implicit module-level singletons.

---

## 11. API and Contract Standards

- REST endpoints use consistent resource naming and HTTP semantics.
- All request/response schemas are typed and versioned where necessary.
- FastAPI OpenAPI is the contract source for generated TypeScript clients.
- List endpoints use cursor pagination for large/changing datasets.
- Filtering, sorting, projection, and maximum page sizes are controlled.
- Mutating endpoints support idempotency keys where duplicate submission is possible.
- Long operations return a job/workflow ID instead of holding the request open.
- Chat streaming uses SSE with resumable event IDs where required.
- Errors use a stable machine-readable structure with safe human messages.
- APIs MUST not expose stack traces, internal IDs unnecessarily, secrets, or unauthorized resource existence.
- Backward-incompatible changes require versioning or an approved migration plan.

---

## 12. High-Traffic and Capacity Engineering

### 12.1 Capacity is designed and measured

Before production, define per customer:

- Daily/monthly active users
- Peak concurrent users
- Requests per second and burst factor
- Chat concurrency
- Connector event rate
- Documents/files per day and maximum size
- Tasks/messages/source objects
- Embedding and indexing throughput
- Report frequency and complexity
- Retention duration
- Acceptable latency/SLOs
- Expected AI token/cost budget

Codex MUST create a capacity model and load-test plan. “High traffic” is not proof of scalability.

### 12.2 Stateless APIs

- API replicas MUST be stateless.
- Session/workflow state belongs in PostgreSQL, Redis, or the durable workflow store.
- Use horizontal scaling behind an AWS ALB/Azure load-balancing service.
- Configure readiness/liveness/startup probes.
- Enforce request timeouts, body limits, and concurrency limits.

### 12.3 Backpressure

Every ingestion and AI pipeline MUST define:

- Maximum queue depth/lag
- Consumer concurrency
- Per-customer/per-connector quotas
- Rate-limit handling
- Pause/degrade policy
- Retry budget
- DLQ behavior
- Autoscaling signal
- Overload response

Do not accept unlimited work into memory. Reject, delay, batch, or spill to a durable queue when capacity is exceeded.

### 12.4 Load testing

Use k6 or Locust for:

- API throughput
- Chat concurrency and streaming
- Connector webhook bursts
- Search and RAG latency
- Database contention
- Queue lag and worker recovery
- Large file ingestion
- Approval/action bursts

Performance regressions beyond approved thresholds fail the release gate.

---

## 13. Kafka Expansion Law

Kafka is part of the scale-out architecture but MUST NOT be deployed initially without a justified event-streaming need. The initial system uses domain events, a transactional outbox, and simple outbox consumers so Kafka can be introduced later without rewriting domain code.

Kafka introduction is **APPROVAL REQUIRED** and should occur when measurements or customer requirements show a need for high-volume durable streams, multiple independent consumers, replay, or long-lived event history.

Approved Kafka use cases:

- Normalized connector/domain event stream
- High-volume activity/change events
- Audit/event export stream where appropriate
- Metrics/analytics pipelines
- Search/index update streams with multiple consumers
- Data lake/warehouse integration
- Reprocessing/replay of event history

Kafka rules:

- Topics are domain-oriented and versioned.
- Events use a schema contract (Pydantic plus JSON Schema, Avro, or Protobuf according to approved ADR).
- Schema compatibility is enforced.
- Partition keys preserve required ordering, such as source object/project/department.
- Consumers are idempotent.
- Consumer groups have clear ownership.
- Offsets are committed only after safe processing.
- Poison messages go to a quarantine/DLQ topic with diagnostics.
- Retention and compaction are intentional.
- Monitor broker health, throughput, partition skew, consumer lag, retries, and processing time.
- Sensitive data is minimized and protected; events do not become an uncontrolled data copy.
- “Exactly once” claims require proof; default to at-least-once plus idempotency.

When introduced, Kafka MUST NOT be used as a synchronous request/response transport or as the primary database.

---

## 14. RabbitMQ Law

RabbitMQ MUST be used for commands, background jobs, work queues, controlled retries, priority work, and tasks where one worker/group should perform the job.

Approved RabbitMQ use cases:

- Connector synchronization commands
- File parsing/OCR jobs
- Embedding batches
- Report generation
- Notification delivery
- Approved external action execution
- Scheduled/retryable operational tasks
- Short/medium-lived agent workflow jobs where a durable workflow engine is not required

RabbitMQ rules:

- Exchanges and routing keys are domain-specific.
- Use durable queues and persistent messages for critical work.
- Consumers acknowledge only after successful safe processing.
- Prefetch is tuned to workload size.
- Retry uses bounded exponential backoff with jitter.
- Dead-letter exchanges/queues are mandatory for critical queues.
- Every job has an idempotency key and attempt count.
- Long jobs store progress/checkpoints outside the message.
- Message payloads are references/minimal data, not huge documents.
- Monitor queue depth, unacked messages, oldest message age, retries, DLQ, throughput, and worker saturation.
- Priority queues are used sparingly.

RabbitMQ MUST NOT duplicate the same responsibility as Kafka without an explicit bridge/flow design.

---

## 15. Domain Events, RabbitMQ, and Future Kafka Boundary

The initial pattern is:

```text
External Change
    ↓
Ingestion Command (RabbitMQ)
    ↓
Fetch + Validate + Store Transaction
    ↓
Transactional Outbox
    ↓
Simple Idempotent Outbox Consumers
    ↓
Search / Metrics / Risk Signals
```

The scale-out pattern after Kafka approval is:

```text
External Change
    ↓
Ingestion Command (RabbitMQ)
    ↓
Fetch + Validate + Store Transaction
    ↓
Transactional Outbox
    ↓
Domain Event Stream (Kafka)
    ↓
Independent Consumers: Search / Metrics / Risk Signals / Audit Export
```

Rules:

- RabbitMQ says: **perform this work**.
- Kafka says: **this fact happened**.
- PostgreSQL remains the transactional system of record.
- The outbox relay prevents database commit/event publication gaps.
- Inbox/deduplication records protect consumers from duplicates.
- Do not dual-publish directly from business code to brokers.
- Broker bridges and failure recovery require integration tests.

---

## 16. Database and Buffering Law

### 16.1 PostgreSQL

PostgreSQL is the authoritative transactional database.

Rules:

- Schema changes use Alembic migrations.
- Foreign keys, unique constraints, checks, and transactions protect integrity.
- Every query is organization hierarchy/ACL aware where required.
- PostgreSQL RLS is defense in depth.
- Indexes follow real query patterns and are verified with execution plans.
- Avoid N+1 queries.
- Use optimistic locking/version columns for concurrent edits where applicable.
- Use short transactions; never keep transactions open across LLM/network calls.
- Pagination is mandatory for unbounded lists.
- High-volume append tables may be partitioned by time or approved business dimension.
- Archive/retention strategies are defined before tables grow uncontrollably.

### 16.2 Database connection buffer/pool

- Use SQLAlchemy async pool with explicit limits.
- Production SHOULD use PgBouncer or an approved managed connection proxy when replica/worker counts can exceed safe database connections.
- Each process has bounded pool size and overflow.
- Total possible application connections MUST remain below the database budget with reserve for administration/migrations.
- Monitor active/idle/waiting connections, pool wait time, transaction duration, locks, deadlocks, and slow queries.
- Autoscaling MUST consider database connection budget; adding API pods must not overload PostgreSQL.

### 16.3 Write buffering and batching

High-volume writes MUST NOT hit PostgreSQL one row at a time when safe batching is possible.

Use:

- Durable broker buffering for ingestion bursts
- In-memory micro-batches only with bounded size/time and safe recovery semantics
- PostgreSQL `COPY` or bulk insert/upsert for large imports
- Batch embedding/index updates
- Transactional outbox for events
- Redis only for ephemeral counters/coordination, never as the sole durable buffer for critical data

Every batch has maximum item count, byte size, wait time, retry policy, idempotency, partial-failure handling, and metrics.

### 16.4 Read scaling and caching

- Use Redis for safe short-lived caching, rate limiting, locks, and computed read models.
- Cache keys include user/access-policy/configuration versions when data is permission-dependent.
- Define TTL, invalidation event, stale-data tolerance, and stampede protection.
- Never share cached AI/search results across incompatible authorization scopes.
- Use database read replicas only for workloads that tolerate replication lag.
- Precompute/materialize expensive dashboards when justified.

---

## 17. Redis Law

Approved uses:

- Rate limiting
- Distributed locks with bounded leases where necessary
- Short-lived session and streaming coordination
- Cached configuration/access context
- Cached dashboard/read models
- Idempotency acceleration backed by durable records when critical
- Provider response cache only when privacy and freshness permit

Redis MUST NOT be the only store for:

- Audit history
- Approvals
- Official workflow state
- Critical job payloads
- Company configuration
- Source-of-truth tasks/projects

All Redis data must have ownership, TTL/persistence decision, invalidation rules, key namespace, and memory limit/eviction policy.

---

## 18. Connector and Ingestion Law

Every connector MUST implement:

- Typed capability contract
- Authentication/OAuth handling
- Least-privilege scopes
- Initial full sync
- Incremental cursor sync
- Webhooks when available
- Scheduled reconciliation
- Rate-limit awareness
- Idempotent event/object handling
- Deletion/tombstone handling
- ACL/permission synchronization
- Raw source reference/payload policy
- Canonical mapping
- Health/freshness status
- Retries and DLQ
- Read and write capabilities separated

Connector data is untrusted input. Validate, normalize, classify, and authorize it before use.

---

## 19. Agentic AI Constitution

### 19.0 Modern agentic target architecture

The target is a modern, governed agentic architecture—not a collection of independent chatbots.

Required logical layers:

```text
Chat / API / Scheduled Trigger / Event
                ↓
Authentication + AccessContext + DomainContext
                ↓
Intent Classification and Request Policy
                ↓
Deterministic Orchestrator / LangGraph Workflow
                ↓
Specialized Skills and Typed Tools
                ↓
Retrieval / Business Services / External Connectors
                ↓
Guardrails + Trust + Citation + Human Approval
                ↓
Response / Approved Action / Checkpoint / Audit
```

Target capabilities:

- Deterministic routing where rules are known
- Stateful LangGraph workflows where reasoning/branching/pause/resume is required
- Logical specialized skills instead of a separate autonomous service per business role
- Supervisor/worker or planner/executor patterns only where evaluation proves value
- Typed shared state
- Durable checkpoints
- Event-triggered, scheduled, and chat-triggered workflows
- Human approval nodes
- Tool permission boundaries
- Short-term working memory separated from durable organizational records
- Step/time/token/cost budgets
- Parallelism with bounded concurrency
- Retry, fallback, circuit breaker, cancellation, and safe terminal states
- Full traces and evaluation

The final graph/topology remains an approval-required design. The architecture MUST allow a workflow to evolve from deterministic orchestration to selected agentic nodes without rewriting domain services.

### 19.1 Architecture approval

The production agent architecture is **APPROVAL REQUIRED**. Before implementation, Codex MUST propose and review with the user:

- Single agent versus workflow versus multi-agent need
- Agent graph
- State schema
- Nodes and edges
- Router/supervisor approach
- Tool contracts
- Memory model
- Checkpoint/persistence strategy
- Human approval nodes
- Failure/retry/fallback paths
- Step/time/token/cost budgets
- Guardrails
- Evaluation plan
- Observability/tracing

No multi-agent system may be introduced merely because the product has many business roles. Prefer deterministic workflows and logical skills unless independent reasoning roles provide measurable value.

### 19.2 LangChain and LangGraph

- LangChain SHOULD provide model/tool/retriever abstractions where useful.
- LangGraph MUST be used for approved stateful, checkpointed, branching, long-running, or human-in-the-loop agent workflows.
- LangGraph state MUST be typed.
- Nodes MUST have one clear responsibility.
- Edges/routers MUST return structured decisions.
- Checkpoints MUST support resume after failure or human pause.
- Graphs MUST have termination conditions and step budgets.
- Tool outputs MUST be typed and validated before re-entering model context.
- Graph definitions, prompts, tools, and model configurations MUST be versioned.

Do not use LangChain/LangGraph wrappers where ordinary Python application code is clearer.

### 19.2A Model access inside agents

Agents and graphs MUST request a model through a logical profile/capability such as `reasoning_llm` or `structured_extraction_llm`. They MUST NOT import or instantiate a vendor client directly.

The Provider Router resolves:

- Approved model profile
- Required capabilities
- Department/project/data-classification policy
- Region/data residency
- Health and rate-limit state
- Cost/latency policy
- Approved fallback order

A fallback MUST be explicit in traces and MUST NOT silently change behavior, privacy, tool capability, or output schema.

### 19.3 Agent rules

- Agents never bypass `AccessContext`.
- Agents receive minimum required context.
- Agents cannot invent tools or call arbitrary code.
- Tools are allowlisted, typed, permission-checked, timeout-limited, and observable.
- Read, draft, write, high-impact, and destructive tools are separated.
- Material decisions/actions pause for human approval.
- Agent output used by code follows strict Pydantic schemas.
- Unstructured model text never directly controls SQL, permissions, routing, or external actions.
- Agents distinguish fact, inference, recommendation, and approved decision.
- Agents attach citations/evidence to material claims.
- Agent loops have hard maximum steps.
- Parallel branches have concurrency limits.
- Failures use controlled retry/fallback; repeated failure reaches a safe terminal state.
- Model/provider fallback must not weaken privacy, data residency, or capabilities silently.

### 19.4 Agent memory

Memory architecture is **APPROVAL REQUIRED**.

Separate:

- Conversation working memory
- Durable conversation summary
- User preferences
- Company/domain configuration
- Workflow state/checkpoints
- Retrieved knowledge
- Official operational records

Conversation memory MUST NOT become organizational truth. Durable memories require provenance, scope, retention, edit/delete behavior, and permission checks.

---

## 20. RAG Constitution

### 20.0A Onyx integration law

Onyx Community Edition/Standard is an approved running component, not merely a reference repository.

Approved responsibilities:

- Enterprise knowledge indexing and search
- Initial vector/keyword retrieval through its Vespa index
- Reusable connectors where their licensing, permissions, and data mappings fit
- Search results, passages, source links, and citations
- Internal RAG/search APIs exposed to the platform adapter

Prohibited responsibilities:

- Official company hierarchy or reporting lines
- Platform authorization source of truth
- Official project/task/risk/decision/quality/approval/action records
- Industry Pack and DomainContext ownership
- Human approval policy
- Direct autonomous external actions outside platform policy

Integration rules:

- Access Onyx through an authenticated internal API/service account and `KnowledgeSearchPort`.
- Pin the Onyx version; upgrades require staging compatibility, migration, API contract, search-quality, permission, and rollback tests.
- Do not couple platform database migrations to Onyx internal tables.
- Do not fork/change Onyx core unless the requirement cannot be met through APIs, connectors, configuration, or a narrow extension. Any fork requires an ADR and upstream-sync strategy.
- Preserve Onyx CE license notices and review the license/edition boundary before copying or modifying code.
- Platform `AccessContext` is authoritative. Queries must carry the narrowest permitted scope/filter; returned results are revalidated before model context/citation delivery.
- If Onyx cannot enforce a required organizational ACL safely, fail closed or use a controlled per-scope ingestion/search design. Never retrieve broadly and rely only on the LLM to hide data.
- Canonical source files, elements, ACLs, versions, and provenance remain exportable/rebuildable outside Onyx.

### 20.0B Unstructured OSS parsing law

Unstructured OSS is the primary parser behind `DocumentParser`.

Execution model:

- Dedicated parsing workers, not the synchronous FastAPI request path
- RabbitMQ jobs with idempotency, retry limits, DLQ, progress, cancellation, and resource limits
- `fast` strategy for text PDFs when appropriate
- `ocr_only` for scanned/image documents
- `hi_res` for complex layout/tables when justified
- Arabic and English Tesseract language packs initially
- File-type-specific/native fallback when Unstructured output fails quality rules

Every parsed element is normalized to a platform model containing stable element ID, document/version ID, element type, text, page/sheet/row, coordinates where available, table representation, parser/version/strategy, source locator, confidence/quality flags, ACL/classification, and checksum.

Unstructured output is untrusted extracted data. It cannot create official tasks, risks, decisions, managers, budgets, quality results, or permissions without structured candidate validation and human approval.

### 20.0C Document-first PM law

External task platforms are optional. The complete product MUST work for a company, department, or project whose operational truth exists only in PDFs, Excel files, Office documents, scans, emails, and reports.

The RAG/PM pipeline must support:

- Direct cited questions over documents
- Project/document collections and version history
- Extracting proposed projects, phases, milestones, tasks, owners, dates, budgets, risks, issues, decisions, dependencies, actions, KPIs, quality gates, and approvals
- Cross-document entity resolution and conflict detection
- Manager validation tasks and HITL activation
- Status/risk/quality reports using document evidence
- Refresh/re-extraction when a new file version arrives
- Clear separation of source-stated facts, AI inference, and human-approved records

Dashboards must not falsely show “no data” merely because no Jira/Asana connector exists. They use approved extracted records, document freshness, evidence coverage, conflicts, and cited inferences according to configured policy.

### 20.0 Modern RAG target architecture

The target RAG system MUST support modern retrieval patterns through configurable strategies rather than one fixed pipeline.

Target architecture:

```text
Sources / Uploads / Connectors
            ↓
Versioned Multimodal Ingestion Pipeline
            ↓
Canonical Document + Chunk + Metadata + ACL Store
            ↓
Sparse Index + Dense Vector Index + Optional Graph Relations
            ↓
Query Understanding and Retrieval Router
            ↓
Hybrid Retrieval + Metadata/ACL Filters
            ↓
Fusion + Deduplication + Reranking
            ↓
Parent/Neighbor Context Expansion and Compression
            ↓
Grounded Generation + Citations + Trust Evaluation
            ↓
Feedback + Offline/Online Evaluation + Reindex Lifecycle
```

The system SHOULD be able to configure and evaluate:

- Fixed, recursive, semantic, layout-aware, hierarchical, and parent-child chunking
- Dense search
- BM25/sparse search
- Hybrid retrieval with Reciprocal Rank Fusion or an approved fusion method
- Metadata and time filtering
- Query rewriting and decomposition
- Multi-query retrieval
- HyDE where evaluation shows value
- Cross-encoder/managed reranking
- Contextual compression
- Parent-document/neighbor expansion
- Table-aware retrieval
- Multilingual retrieval
- Multi-modal document retrieval where required
- Graph-assisted retrieval/GraphRAG only for suitable relationship-heavy use cases
- SQL/structured-data routing
- Citation and attribution validation
- Answer abstention when evidence is insufficient

No advanced technique is enabled only because it is modern. Each technique MUST be feature-configurable and evaluated against quality, latency, cost, and operational complexity.

### 20.1 Architecture approval

The RAG architecture is **APPROVAL REQUIRED** before production implementation. Codex MUST present:

- Supported data types and volumes
- Parsing/OCR/table strategy
- Chunking strategies by document type
- Metadata and ACL design
- Embedding candidates
- Vector database candidates
- Sparse/full-text search design
- Hybrid retrieval and fusion
- Reranking strategy
- Query routing/rewriting
- Parent-child/context expansion
- Citation design
- Freshness/deletion/reindex flow
- Evaluation dataset and metrics
- Cost, latency, scalability, and cloud tradeoffs

### 20.2 Ingestion pipeline

Required stages:

```text
Upload/Connector
→ Malware and Type Validation
→ Raw Object Storage
→ Parse/OCR/Layout/Table Extraction
→ Cleaning and Deduplication
→ Metadata + ACL + Classification
→ Document-Type Chunking
→ Embedding Batches
→ Sparse + Vector Indexing
→ Validation
→ Active Index Version
```

Each stage is idempotent, retryable, observable, versioned, and supports failure recovery.

### 20.3 Retrieval

The retrieval router MUST choose among:

- PostgreSQL structured queries
- Full-text/BM25 keyword search
- Dense vector search
- Hybrid sparse+dense retrieval
- Graph/dependency traversal if approved
- Live connector fetch for freshness-critical data

Required retrieval order:

1. Authenticate and calculate access scope.
2. Resolve saved DomainContext.
3. Apply organizational-unit, project, ACL, classification, source, and time filters **before retrieval**.
4. Retrieve candidates.
5. Fuse/deduplicate.
6. Rerank only when the active retrieval profile enables a reranker; initial profile may pass through without reranking.
7. Expand parent context.
8. Revalidate access and freshness.
9. Construct minimal model context.
10. Generate cited response.

### 20.4 Knowledge index and vector database law

Onyx Community Edition/Standard with its Vespa-backed vector/keyword index is the approved initial knowledge-search path. The platform MUST access it through `KnowledgeSearchPort` and authenticated Onyx APIs. Direct queries to Onyx or Vespa internal databases/indexes from business modules or LangGraph nodes are prohibited.

Platform PostgreSQL remains the official system of record for company hierarchy, projects, approved tasks, risks, decisions, quality records, approvals, actions, and canonical provenance. Onyx/Vespa is a derived searchable knowledge index that must be rebuildable from canonical sources and stored files.

Do not run a multi-database proof of concept before it is needed. Evaluating or activating another vector/search store is **APPROVAL REQUIRED** and is triggered only by evidence such as:

- Onyx/Vespa cannot meet measured latency/throughput/index-size or authorization requirements
- Required hybrid/lexical capabilities cannot be met cleanly
- Customer cloud policy mandates a managed search service
- Operational isolation, availability, or scaling requirements justify another system
- Representative retrieval evaluation shows a meaningful quality advantage

When triggered, the shortlist MAY include Azure AI Search, OpenSearch, PostgreSQL + pgvector, Qdrant, or another approved managed/self-hosted option.

Selection criteria:

- Mandatory ACL/metadata filtering correctness
- Hybrid search quality
- HNSW/index capabilities and tuning
- Horizontal/vertical scaling
- Index build/update/delete behavior
- Backup/restore and disaster recovery
- Multi-index/version support
- Operational complexity
- Observability
- Data residency/security
- Cloud portability/lock-in
- Latency and throughput under representative load
- Total cost

Required capabilities:

- Strong metadata filters
- Namespace/collection/index isolation by approved scope
- Batched upsert/delete
- Stable document/chunk/version identifiers
- Embedding model/version tracking
- Reindex without unsafe downtime
- Tombstone and permission-revocation propagation
- Configurable HNSW or equivalent ANN parameters
- Exact-search mode for evaluation subsets where supported
- Index health, size, latency, and recall monitoring

RAG/application code uses `KnowledgeSearchPort` and logical retrieval profiles, not Onyx/Vespa internals or vendor collection names. This preserves future expansion without operating duplicate indexes today.

### 20.4A Embedding model law

Embedding providers and models are selectable through the Embedding Provider Registry and versioned embedding profiles.

An embedding profile includes:

- Provider and model
- Endpoint/region
- Secret reference
- Dimension
- Maximum input length
- Batch limits
- Normalization/distance requirements
- Supported languages/modalities
- Cost and rate limits
- Data privacy/residency policy
- Intended document/query types

The query embedding model MUST be compatible with the active document index version. Configuration validation MUST prevent mismatched dimensions or embedding spaces.

Embedding selection requires evaluation on the customer's representative languages and documents, including Arabic/English when required. Measure retrieval quality, latency, throughput, batch efficiency, cost, and operational constraints.

### 20.4B Retrieval profiles

RAG behavior MUST be controlled through versioned retrieval profiles, for example:

- `policy_document_search`
- `project_status_evidence`
- `event_operations_search`
- `construction_contract_search`
- `cross_department_executive_search`

A profile can define:

- Sparse/dense/hybrid strategy
- Embedding/index profile
- Metadata filters
- Top-K candidate counts
- Fusion method
- Reranker profile
- Score thresholds
- Parent/neighbor expansion
- Context/token budget
- Citation requirements
- Freshness limits
- Allowed query rewriting methods

Profiles are activated through evaluation and human approval, not prompt changes hidden in code.

### 20.5 RAG quality evaluation

Required offline metrics:

- Recall@K
- Precision@K
- MRR/NDCG where applicable
- ACL correctness
- Citation correctness
- Faithfulness/groundedness
- Answer relevance and completeness
- No-answer correctness
- Freshness/deletion correctness

Required online signals:

- Retrieval latency
- Rerank latency
- Empty/low-score retrieval rate
- Citation click/use
- User feedback
- Unsupported-claim indicators
- Cost and tokens
- Drift in query types

Any embedding, chunking, reranker, prompt, vector-index, or model change MUST run regression evaluation before release.

---

## 21. Human-in-the-Loop Law

Human-in-the-loop is mandatory for material configuration, decisions, communications, and actions.

Agents MAY:

- Read authorized information
- Analyze and calculate
- Detect issues
- Recommend
- Extract configuration candidates
- Draft messages, tasks, reports, or changes

Agents MUST NOT self-approve:

- Company/hierarchy configuration
- Permissions/classification
- Official project decisions
- Scope/baseline/budget/milestone changes
- Risk acceptance/closure
- Quality-gate override or handover
- External communications/escalations
- External tool writes
- Employee-impacting decisions
- Financial/legal/safety/destructive actions

Approval requirements:

- Show before/after values.
- Show evidence, confidence, and uncertainty.
- Show affected resources/people and expected impact.
- Resolve approvers deterministically from policy/hierarchy.
- Support edit/reject/comment/request clarification.
- Support sequential, parallel, group, and four-eyes approval.
- Revalidate permissions and source state before execution.
- Expire approval when material inputs change.
- Record immutable audit history.
- Never auto-approve after SLA escalation.

---

## 22. Security and Data Isolation Law

- Every data access begins with server-derived `AccessContext`.
- Client-provided department/project IDs are filters, never authorization.
- Apply RBAC + hierarchy + project membership + source ACL + classification + explicit grants/denies.
- Explicit deny overrides allow.
- Authorization happens before SQL/search/vector retrieval and before LLM context.
- Search/vector indexes include mandatory access metadata filters.
- Managers see authorized descendant scope, not unrestricted company data.
- C-Level/Board access is policy-driven.
- Secrets use AWS Secrets Manager or Azure Key Vault.
- Encrypt in transit and at rest.
- Validate webhook signatures.
- Protect against SSRF, injection, malicious files, prompt injection, and data exfiltration.
- Retrieved documents are untrusted data, never system instructions.
- No secrets or unnecessary personal data in prompts/logs.
- Audit sensitive access and every material action/approval.
- Run cross-department and restricted-classification security tests.

---

## 23. Testing Constitution

Every feature MUST include tests proportional to risk.

Required levels:

- Unit tests for domain logic and policies
- Integration tests for database, Redis, RabbitMQ, object storage, search/vector adapters, and Kafka only when enabled
- Contract tests for connectors/providers
- API tests
- Authorization and hierarchy isolation tests
- Migration tests
- Idempotency/duplicate-delivery tests
- Failure/retry/DLQ tests
- End-to-end critical workflow tests
- Load/performance tests
- AI/RAG regression evaluations
- Security tests

Use testcontainers or equivalent for realistic infrastructure tests. Do not mock away the behavior that a test is supposed to verify.

Tests MUST cover happy path, validation failure, unauthorized access, conflict/concurrency, provider failure, retry exhaustion, stale approval, duplicate message, and partial batch failure where relevant.

A bug fix requires a regression test.

---

## 24. Observability Constitution

Every critical workflow MUST produce:

- Structured logs
- Metrics
- Distributed traces
- Correlation/request/workflow IDs
- Safe error classification
- Business outcome/event

Trace examples:

```text
API → Authorization → Use Case → DB/Cache → Response
Webhook → RabbitMQ Job → Source Fetch → DB → Outbox → Consumers (Kafka after approved expansion)
Chat → Access → Retrieval → Rerank → LLM → Guardrail → Approval/Response
```

Monitor:

- API latency/errors/traffic/saturation
- Database pool/query/lock health
- Redis health/hit rate/memory
- Kafka broker/partition/consumer lag when Kafka is enabled
- RabbitMQ queue age/depth/DLQ
- Worker concurrency/failures
- Connector freshness/rate limits
- Search/vector latency/index health
- LLM latency/tokens/cost/errors
- Agent steps/tool failures/loops
- RAG retrieval/citation/quality signals
- Approval wait time/action success

Sensitive payloads are redacted. Full prompts/source text are not logged by default.

---

## 25. Resilience and Failure Handling

- Classify errors as validation, authorization, conflict, transient provider, permanent provider, rate limit, timeout, or internal defect.
- Retry only transient/retryable errors.
- Retries are bounded and idempotent.
- Use circuit breakers and bulkheads for external dependencies.
- Define fallback behavior explicitly; fallback must not weaken security/privacy.
- Critical workflows checkpoint progress.
- Partial failure returns a clear result and recovery path.
- Degraded services show freshness/availability status.
- Never report success before durable commit/external confirmation.
- External write results are reconciled when acknowledgment is uncertain.

---

## 26. Data Consistency and Idempotency

Required idempotency targets:

- Webhook events
- Connector sync pages/objects
- Kafka consumers when enabled
- RabbitMQ jobs
- File processing stages
- Embedding/index writes
- Notifications
- Report generation where duplicate output is harmful
- Approval submissions
- External actions

Use stable idempotency keys, unique constraints, inbox records, action versions, and safe upserts. Document whether each workflow provides strong consistency, eventual consistency, or compensating behavior.

---

## 27. Configuration and Feature Flags

- Configuration is typed and validated on startup.
- Environment-specific settings are explicit.
- Secrets are references, not committed values.
- Feature flags have owner, purpose, default, expiry/removal plan, and audit needs.
- Company/department configuration is versioned and activated, not mutated invisibly.
- Normal chat reads precompiled DomainContext; it does not infer industry/activity again.
- Configuration changes invalidate dependent caches and read models safely.

---

## 28. Database Migration Law

- Every schema change uses Alembic.
- Migrations are reviewed, reversible where practical, and tested on representative data volume.
- Large-table changes use expand/migrate/contract rather than long blocking operations.
- Backfills are resumable, batched, observable, and rate-limited.
- Application versions remain compatible during rolling deployment.
- Destructive column/table removal requires verified migration, retention decision, backup, and approval.

---

## 29. CI/CD Quality Gates

Every pull request MUST pass:

- Formatting
- Linting
- Type checking
- Unit and integration tests
- Migration validation
- Dependency/security scanning
- Secret scanning
- Container scanning
- Architecture/import-boundary checks
- Documentation checks for public functions/methods
- Required AI/RAG regression suite when affected
- Required performance tests when a hot path changes

Deployment stages:

```text
Development
→ Automated Tests
→ Security/Quality Gates
→ Staging
→ Migration/Smoke/Evaluation
→ Human Release Approval
→ Production
→ Post-deployment Verification
```

Use rolling, canary, or blue/green deployment according to risk. Production rollback and database compatibility are planned before release.

---

## 30. Documentation Law

Codex MUST maintain:

- README and local setup
- Architecture overview
- Module documentation
- OpenAPI contract
- ADRs
- Database schema/migration notes
- Domain event/outbox catalog, plus Kafka topic catalog when Kafka is enabled
- RabbitMQ exchange/queue/job catalog
- Connector contracts
- Agent graph/state/tool documentation
- RAG ingestion/retrieval/index documentation
- Approval policies
- Security and access model
- Runbooks and incident procedures
- Capacity model and load-test results
- Deployment and rollback guides

Documentation changes are part of implementation, not a later task.

---

## 31. Definition of Done

A story is not Done until:

- Acceptance criteria pass.
- Architecture follows module boundaries.
- Code follows SOLID/OOP/clean-code rules.
- Every function/method/class has a useful docstring.
- Types and validation are complete.
- Authorization and data classification are enforced.
- Human approval exists where required.
- Idempotency and failure behavior are defined.
- Tests pass at required levels.
- Logs, metrics, and traces exist.
- Migrations and rollback/compatibility are addressed.
- Documentation is updated.
- Security/privacy review is satisfied.
- Load impact is evaluated for hot/high-volume paths.
- AI/RAG evaluation passes when applicable.
- No unresolved critical/high defects remain.

---

## 32. Prohibited Practices

Codex MUST NOT:

- Build the entire platform in one generation/phase
- Create a microservice per agent
- Use Kafka and RabbitMQ interchangeably
- Publish directly to Kafka before the database transaction is safely represented in an outbox
- Store critical state only in Redis
- Perform row-by-row high-volume imports without batching
- Run unbounded worker concurrency
- Use unbounded queues, retries, context, agent steps, or result sets
- Put business logic in API routes
- Couple domain logic to cloud/provider SDKs
- Let agents generate and execute unrestricted SQL/code
- Let LLM output directly change permissions or external systems
- Retrieve data before applying permissions
- Use vector similarity as proof of authorization
- Log secrets or full sensitive prompts by default
- Swallow exceptions
- Use broad mocks as proof that infrastructure integration works
- Merge code without tests, types, documentation, and observability
- Select the agent/RAG/vector architecture without review and approval
- Treat AI suggestions as official decisions

---

## 33. Required Codex Workflow for Every Implementation Phase

Before coding, Codex MUST return:

1. Scope and assumptions
2. Existing repository assessment
3. Proposed architecture and affected modules
4. Data model/migration impact
5. API/event/job contracts
6. Security and authorization impact
7. Capacity and failure considerations
8. Human approval requirements
9. Test plan
10. Observability plan
11. Documentation changes
12. Open decisions requiring approval

During coding, Codex MUST:

- Implement in small reviewable increments
- Preserve unrelated existing work
- Run relevant checks frequently
- Record significant decisions
- Stop at approval-required architecture decisions

After coding, Codex MUST report:

- What changed
- Files/modules changed
- Architecture decisions made
- Tests/checks executed and exact results
- Migrations/deployment notes
- Performance/security considerations
- Known limitations and remaining work
- Documentation updated

---

## 34. Architecture Decisions That Must Be Reviewed Together

The following decisions are intentionally open and MUST be reviewed with the user before implementation:

1. Final agent topology and LangGraph design
2. Agent state, checkpoint, and memory architecture
3. Final RAG ingestion and retrieval architecture
4. Vector database selection
5. Search engine and hybrid retrieval implementation
6. Embedding and reranking models
7. Graph database need
8. Kafka provider/topology/topic/schema design
9. RabbitMQ topology and worker framework
10. PostgreSQL sizing, PgBouncer/proxy, partitioning, and replica strategy
11. AWS versus Azure reference deployment
12. LLM/provider routing and data-residency policy
13. Observability products beyond OpenTelemetry
14. Microservice extraction boundaries
15. Disaster recovery targets and backup design
16. Additional LLM/embedding/vector/reranker adapters beyond the approved initial baseline
17. Provider fallback and detailed data-residency rules per customer deployment
18. Simple AI/knowledge settings roles and approval workflow
19. Exact OpenAI model names initially and future Azure/AWS profiles after capability, region, cost, and evaluation review
20. Exact BGE reranker model and managed fallback after multilingual evaluation

Codex must prepare options, recommendations, tradeoffs, diagrams, costs, operational risks, and a proof-of-concept plan where appropriate. No decision is final merely because it appears in example code.

---

## 35. Instruction Prompt for Codex

Use this prompt with this constitution and the master specification:

> Treat `CODEX_ENGINEERING_CONSTITUTION.md` as mandatory engineering law and `AI_OPERATIONS_PLATFORM_MASTER_SPEC.md` as the product source of truth. Build the complete target architecture incrementally and local-first with Docker Compose, without requiring cloud services during development. Use the platform's Python/FastAPI, Next.js/TypeScript, PostgreSQL, Redis, RabbitMQ, and MinIO core. Use Onyx Community Edition/Standard as the initial internal enterprise knowledge/search and connector engine through an authenticated `KnowledgeSearchPort`; use its Vespa index and do not run a duplicate pgvector RAG index without an approved separate need. Use Unstructured OSS in isolated RabbitMQ workers for PDF/Office/image parsing, OCR, layout, and tables, then normalize results into canonical elements with provenance and ACL metadata. Use OpenAI initially for LLMs/embeddings behind interfaces. Use LangChain/LangGraph for approved modern RAG/agent orchestration, typed state, checkpoints, and human-in-the-loop; never let graph/provider internals own business truth. Support document-first projects with no task-platform connector as completely as tool-connected projects. Keep storage, knowledge search, parsing, models, embeddings, queues, and cloud services behind ports so Kubernetes deployment and later AWS/Azure adapters—including S3/Blob, Bedrock/Azure OpenAI, OpenSearch/Azure AI Search, and managed document intelligence—do not require rewriting core modules. Apply OOP, SOLID, clean code, types, docstrings, bounded concurrency, backpressure, batching, idempotency, observability, tests, strict access control before retrieval/model context, and human approval for material decisions/actions. Keep the outbox Kafka-ready and add Kafka only after an approved measured need. Stop for approval on major architecture changes or conflicts.

---

## 36. Review Checklist for This Draft

Before marking this constitution approved, review together:

- Measurable trigger for adding Kafka after the initial outbox/consumer architecture reaches a real scaling or replay need
- Whether RabbitMQ uses Celery or a custom/alternative worker layer
- Whether PgBouncer is mandatory in every deployment
- Preferred managed Kafka option only when Kafka expansion is approved
- Initial performance targets and expected customer size
- Onyx/Vespa local resource sizing, ACL/filter contract, pinned version, and future trigger for evaluating Azure AI Search/OpenSearch/pgvector
- Exact OpenAI model names for each logical profile
- Exact OpenAI embedding model after Arabic/English evaluation
- Whether/when retrieval quality justifies adding BGE local reranking
- Simple AI/knowledge settings authorization and OpenAI secret-rotation workflow
- Exact Onyx API integration boundary, service-account scope, and upstream upgrade strategy
- Unstructured strategy routing, Arabic/English OCR, and document-quality acceptance thresholds
- Agent topology and human-approval graph
- Required code-coverage threshold
- Whether docstrings are mandatory for every private helper or only all public/non-trivial functions
- Lint/type/security tool choices
- Disaster recovery RPO/RTO

Until reviewed, these items remain open decisions and must not be silently fixed by implementation.
