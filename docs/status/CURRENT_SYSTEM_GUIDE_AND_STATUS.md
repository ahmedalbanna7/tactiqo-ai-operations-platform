# Tactiqo — Current system guide and status

Updated: 2026-09-16

## What the home suggestions mean

- **حالة المشروع / البنود المتأخرة** are `planned_knowledge` requests. The graph authorizes the
  employee, retrieves authorized project evidence from RAG, inspects an authorized project tool when
  one is connected, then lets the PMO agent synthesize a cited answer. They are not creation actions.
- **مهمة متابعة** is a planned action. The planner selects an authorized Jira/Trello-style MCP tool,
  validates its arguments and grant, and requests approval when policy requires it before creating
  anything. With no real tenant connection it must fail closed rather than pretending it created a task.

## How to use the current product and expected behavior

1. Open `http://127.0.0.1:13000`. The API is at `http://127.0.0.1:18000`.
2. Use ordinary chat for greetings and simple questions. Expected: a fast route with no planner or
   tools. Model latency still depends on the selected local LM Studio model.
3. Ask about a document fact. Expected: authorized hybrid lexical/vector retrieval, citations and a
   source-preview button. Suspicious document instructions are quarantined.
4. Ask **ما هي الملفات الموجودة؟**. Expected: an immediate inventory without an LLM call. Adding
   **المشروع** filters that inventory to `domain=project`.
5. In **مصادر المعرفة**, choose a domain (project, HR, finance, IT, legal, operations or general) and
   a purpose (authoritative, research or ignored), then upload. Ignored files remain recorded but never
   enter retrieval. The drawer can filter the visible inventory by domain.
6. Uploads up to 100 MB are currently accepted for local testing and parsed asynchronously. The item
   moves through uploaded/processing/ready or failed. Larger production uploads remain a planned
   resumable background-job feature.
7. In **Settings / AI**, discover loaded LM Studio models, select an LLM/embedding profile, test it,
   then activate it. Expected: only an actually loaded compatible model activates; secrets are not
   returned by the API.
8. In **Settings / Integrations**, an Owner/Admin creates a tenant Jira or Slack connection, completes
   OAuth, assigns a connection manager, and grants exact MCP tools to agents/scopes. Expected: tools
   stay invisible until connection, consent and grants are all valid.
9. In **Artifacts**, create governed drafts. Markdown reports plus native DOCX, PPTX and XLSX are live.
   Submit for review, use a different Owner/Admin to approve, then publish/action. Dry-run execution is
   safe; real Jira/Slack action needs a working tenant MCP connection and mapping.
10. Background jobs, organization hierarchy, agent visibility, budgets, artifact policy, templates,
    retention and Legal Hold are exposed through their implemented APIs/settings surfaces. Access is
    recalculated from tenant, employee, department, team, project, classification and explicit grants.

## Delivery status

- **F0–F6:** foundations are implemented: repeatable Docker stack, SaaS identity/organization model,
  policy compiler and agent catalog, replaceable LLM/Embedding banks, adaptive LangGraph routing and
  memory, guardrails/review/fallback controls, durable worker foundation, and tenant-scoped MCP/OAuth
  connection management. Real Jira/Slack success still requires customer credentials and consent.
- **F7:** core is operational, not closed. Live: tenant-scoped originals, parsing for PDF/DOCX/XLSX/
  CSV/PPTX/text/Markdown, versions/chunks/ACL snapshots, pgvector + lexical hybrid retrieval, Arabic/
  English embeddings, citations, secured preview, revocation, injection quarantine and evaluation
  harness. New document domain/purpose metadata and UI filtering are live.
- **F8:** foundation is operational, not closed. Live: artifact/version storage, report templates,
  policy marks, metering facts, retention and Legal Hold, independent review gates, native DOCX/PPTX/
  XLSX, dry-run action lifecycle, retry/compensation contracts and tenant MCP mappings. OpenAI/Claude
  provider slots and capability routing are implemented; LM Studio remains the currently configured
  local provider. No real cloud credential or provider success is certified.

## Explicitly incomplete work

### F7 remaining

- Source connectors and continuous synchronization (beyond upload and separately managed MCP tools).
- OCR for scanned files; audio/video transcription; rich page/table/cell/slide/timestamp locators.
- Authorized-candidate reranker and representative customer evaluation/certification.
- Real membership/connector revocation drills and final Arabic/English quality exit thresholds.
- Resumable multipart upload and durable background processing UI for files above the current 100 MB.

### F8 remaining

- Real external-provider success for Jira, Slack and email under actual tenant OAuth/grants.
- Full email, Power BI, automation, image, video, meeting/calendar, data-operations and social agents.
- Native PDF output; richer Office templates, charts, formulas, notes and visual validation.
- Positive two-person publication test with a second real reviewer, provider-side destination checks,
  real reversal mappings and full F8 exit-gate tests.

## Current verified checkpoint

- API, PostgreSQL, Redis, RabbitMQ, MinIO, Web and Worker containers are running; mandatory API
  dependencies report healthy.
- Migration `20260916_0018` is applied through the compose migration service.
- `F7_IMPLEMENTATION.md` is `project / authoritative` and visible to the current authorized owner.
- Knowledge inventory was exercised through the real API and completed with citations.
- Ruff, mypy, TypeScript, ESLint, production Web build and the focused 50-test suite pass.

This status intentionally distinguishes implemented contracts and dry runs from real third-party
effects. No UI message should claim Jira/Slack work was created until the provider confirms it.
