# Dockerfile de producción para el plano online de Cadenza (#6)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copiar configuración del workspace y dependencias
COPY pyproject.toml uv.lock* ./
COPY apps/api/pyproject.toml apps/api/
COPY packages/application/pyproject.toml packages/application/
COPY packages/domain/pyproject.toml packages/domain/
COPY packages/interchange/pyproject.toml packages/interchange/
COPY packages/learning/pyproject.toml packages/learning/
COPY packages/omr/pyproject.toml packages/omr/
COPY packages/persistence/pyproject.toml packages/persistence/
COPY packages/validation/pyproject.toml packages/validation/

# Copiar el código fuente de paquetes y aplicaciones
COPY apps/ apps/
COPY packages/ packages/

# Instalar dependencias en el entorno virtual
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Etapa final ligera para ejecución
FROM python:3.12-slim-bookworm AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/apps/api/src:/app/packages/application/src:/app/packages/domain/src:/app/packages/interchange/src:/app/packages/learning/src:/app/packages/omr/src:/app/packages/persistence/src:/app/packages/validation/src"

EXPOSE 8000

# En producción: aplicar migraciones Alembic y arrancar FastAPI (#6)
CMD ["sh", "-c", "alembic -c packages/persistence/alembic.ini upgrade head && uvicorn cadenza.api.main:create_default_app --factory --host 0.0.0.0 --port 8000"]
