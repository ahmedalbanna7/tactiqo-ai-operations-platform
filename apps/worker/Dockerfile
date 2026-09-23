FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system tactiqo \
    && useradd --system --gid tactiqo --create-home tactiqo

COPY pyproject.toml uv.lock README.md ./

RUN python -m pip install --no-cache-dir uv==0.11.24 \
    && uv sync --frozen --no-group quality --no-group test \
        --extra infrastructure --extra documents --no-install-project

COPY backend/src ./backend/src
COPY apps/api/src ./apps/api/src
COPY apps/worker/src ./apps/worker/src
COPY apps/mcp_demo/src ./apps/mcp_demo/src
COPY scripts/init_metrics_auth.py ./scripts/init_metrics_auth.py

RUN uv sync --frozen --no-group quality --no-group test \
        --extra infrastructure --extra documents --no-editable \
    && /usr/local/bin/python -m pip uninstall --yes uv

USER tactiqo

CMD ["python", "-m", "tactiqo_worker.main"]
