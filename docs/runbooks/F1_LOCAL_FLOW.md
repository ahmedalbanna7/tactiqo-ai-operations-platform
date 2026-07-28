# F1 Local Functional Flow

## Purpose

Run and verify the chat, MCP approval, document ingestion, and RAG flow without
claiming production identity or authorization readiness.

## Start

From the repository root:

```powershell
docker compose up --build -d
docker compose ps
```

Open `http://localhost:13000`. The API is available at
`http://localhost:18000`, and development OpenAPI documentation is at
`http://localhost:18000/docs`.

The default `deterministic` model provider makes local functional tests
repeatable and does not make paid model calls. To use OpenAI, set these values
in a local `.env` file and restart `api`:

```dotenv
TACTIQO_MODEL_PROVIDER=openai
TACTIQO_OPENAI_API_KEY=replace-locally
TACTIQO_OPENAI_MODEL=gpt-5.6-sol
```

Never commit `.env` or API keys.

## Verify chat and MCP

1. Ask `اعرض حالة المشروع` and confirm a read-only MCP result streams into the
   conversation without an approval prompt.
2. Ask `أنشئ مهمة متابعة لمراجعة الفلو` and confirm the run pauses on an
   approval card.
3. Reject once and verify no success is claimed.
4. Repeat, approve, and verify the tool result appears before completion.

The demonstration MCP mutation is local and ephemeral. Slack, Jira, Trello, and
other external systems are introduced later as authenticated MCP servers behind
the same `ToolGateway` boundary.

## Verify document ingestion and retrieval

1. Attach a `.txt`, `.md`, `.csv`, `.pdf`, `.docx`, or `.xlsx` file under 20MB.
2. Open the Knowledge drawer and wait for `جاهز للبحث`.
3. Ask a question containing meaningful words from the file.
4. Confirm the answer includes a visible citation to the uploaded document.

PostgreSQL remains canonical, MinIO stores originals, RabbitMQ owns parse jobs,
and the local lexical adapter is an explicit development fallback. Set
`TACTIQO_KNOWLEDGE_SEARCH_ENABLED=true` only with an authenticated Onyx service
token.

## Quality gates

```powershell
uv sync --frozen --all-extras --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy backend/src apps/api/src apps/worker/src apps/mcp_demo/src
uv run pytest
pnpm --filter @tactiqo/web lint
pnpm --filter @tactiqo/web typecheck
pnpm --filter @tactiqo/web build
docker compose config --quiet
```

## Troubleshooting

- Check `docker compose ps` before debugging application code.
- Use `docker compose logs api worker mcp-demo migrate` for redacted process
  errors. Do not paste secrets into issues or chat.
- Failed parsing is retried three times and then dead-lettered to
  `knowledge.parse.v1.dlq`; the document shows a safe failure code.
- A run waiting for approval is intentionally paused and can be cancelled from
  the chat UI.
