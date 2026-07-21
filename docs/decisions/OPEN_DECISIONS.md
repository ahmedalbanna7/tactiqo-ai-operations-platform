# Open Decision Register

Status values: `OPEN`, `DISCOVERY`, `READY FOR REVIEW`, `APPROVED`, `DEFERRED`.
Only an explicit human decision can move an item to `APPROVED`.

## Decisions needed for Phase 0/1

| ID | Decision | Status | Needed before |
|---|---|---|---|
| DEC-001 | Confirm repository/project folder name (`Tactiqo` is temporary) | DISCOVERY | public naming/release |
| DEC-002 | Select PostgreSQL hierarchy query model: `ltree` or closure table | OPEN | hierarchy production schema |
| DEC-003 | Select RabbitMQ worker framework and initial topology | OPEN | production job implementation |
| DEC-004 | Define local/CI code coverage threshold | OPEN | final CI release gate |
| DEC-005 | Confirm private-helper docstring rule | OPEN | final lint/docs gate |
| DEC-006 | Confirm MVP identity provider and local authentication strategy | OPEN | authentication implementation |
| DEC-007 | Confirm initial customer capacity envelope and connection budget | OPEN | performance and pool configuration |
| DEC-008 | Confirm initial RPO/RTO and backup/restore targets | OPEN | production-ready data design |

## Product discovery decisions

| ID | Decision | Status | Needed before |
|---|---|---|---|
| DEC-101 | Final product/company name | DISCOVERY | branding/public release |
| DEC-102 | First pilot industry and project lifecycle | OPEN | first non-General Industry Pack |
| DEC-103 | First work-management connector and approved write action | OPEN | connector Phase 2/6 |
| DEC-104 | First communication/document/email-calendar connectors | OPEN | MVP connector backlog |
| DEC-105 | English-only or English/Arabic MVP | OPEN | UX, OCR, retrieval evaluation |
| DEC-106 | Required compliance regimes | OPEN | controls and evidence plan |
| DEC-107 | Commercial packaging and usage governance | DISCOVERY | product operations |

## Architecture decisions explicitly requiring approval

| ID | Decision | Status | Needed before |
|---|---|---|---|
| DEC-201 | Final RAG ingestion/retrieval, ACL, chunking, fusion, and citation architecture | OPEN | Phase 3 production implementation |
| DEC-202 | Exact Onyx API boundary, version, ACL/filter contract, sizing, and upgrade strategy | OPEN | Onyx integration |
| DEC-203 | Embedding model/profile after representative Arabic/English evaluation | OPEN | production indexing |
| DEC-204 | Reranker need and model after retrieval evaluation | DEFERRED | reranking activation |
| DEC-205 | Agent/LangGraph topology, typed state, tools, budgets, HITL nodes, and evaluation | OPEN | Phase 4 agent workflows |
| DEC-206 | Agent checkpoint and memory architecture | OPEN | durable workflows/memory |
| DEC-207 | Additional LLM, embedding, vector, parser, or reranker adapters | DEFERRED | adapter expansion |
| DEC-208 | Kafka trigger, provider, topology, schemas, and retention | DEFERRED | event-stream expansion |
| DEC-209 | Graph database need | DEFERRED | any graph-store introduction |
| DEC-210 | Microservice extraction boundary | DEFERRED | any service extraction |
| DEC-211 | AWS versus Azure and customer/provider account ownership | OPEN | cloud implementation |
| DEC-212 | Provider routing, fallback, regions, privacy, and data residency | OPEN | production model access |
| DEC-213 | PostgreSQL sizing, PgBouncer, partitioning, replicas, and managed proxy | OPEN | production deployment |
| DEC-214 | Observability products beyond OpenTelemetry | OPEN | production operations stack |

## Decision process

For every decision, prepare:

1. Problem, constraints, and decision deadline.
2. Options and explicit non-options.
3. Security, privacy, access, and human-approval impact.
4. Cost, performance, scalability, reliability, and operational trade-offs.
5. Migration, rollback, and portability impact.
6. Proof-of-concept and evaluation plan where applicable.
7. Recommendation.
8. Explicit human approval and an ADR when approved.
