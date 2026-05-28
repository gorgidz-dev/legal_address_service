# syntax=docker/dockerfile:1.6
# Backend FastAPI image. Минимальный prod-образ: Python 3.12-slim + uvicorn.
# Миграции в этом образе не запускаются автоматически — отдельная команда:
#   docker compose run --rm backend alembic upgrade head

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Системные пакеты: libpq-dev для asyncpg/psycopg сборки не нужны (asyncpg ставится колесом),
# но Pillow требует libjpeg/zlib. Минимум.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

# Non-root user.
RUN useradd --create-home --uid 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 2 воркера хватает на 100-300 DAU. Меняй через docker compose command.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
