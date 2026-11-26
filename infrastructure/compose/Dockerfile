FROM python:3.11.18-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY packages ./packages
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY workers ./workers
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.11.18-slim-bookworm AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY packages/agentgenome/migrations ./packages/agentgenome/migrations
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"
CMD ["uvicorn", "apps.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
