# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.0 AS uv

FROM python:3.12.14-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM python:3.12.14-slim-bookworm AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV HOME=/home/csight \
    PATH=/app/.venv/bin:${PATH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_SYNC=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN groupadd --gid "${APP_GID}" csight \
    && useradd --create-home --uid "${APP_UID}" --gid "${APP_GID}" csight

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

COPY --from=builder --chown=csight:csight /app/.venv /app/.venv
COPY --chown=csight:csight pyproject.toml uv.lock ./
COPY --chown=csight:csight app ./app
COPY --chown=csight:csight alembic ./alembic
COPY --chown=csight:csight alembic.ini ./alembic.ini

USER csight

EXPOSE 8000

STOPSIGNAL SIGTERM

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
