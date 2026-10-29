FROM ghcr.io/astral-sh/uv:0.8.13 AS uv

FROM python:3.15.0-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api ./api
COPY shared ./shared
COPY workers ./workers
COPY alembic.ini ./
RUN uv sync --frozen --no-dev && \
    useradd --create-home --uid 10001 app

USER app

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
