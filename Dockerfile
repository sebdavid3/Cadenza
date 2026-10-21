# Dockerfile de producción para el plano online de Cadenza (#6, ADR-0015, ADR-0018)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never

# `uv sync --frozen` necesita todos los miembros del workspace
COPY pyproject.toml uv.lock ./
COPY apps/api/ apps/api/
COPY packages/ packages/

# La raíz del workspace es un proyecto virtual sin dependencias propias (los paquetes
# solo figuran en el grupo dev): se instala el paquete de la API con el extra de HOMR,
# el único motor OMR (#135).
RUN uv sync --frozen --no-dev --package cadenza-api --extra homr

# Descarga los pesos de HOMR en la imagen para no depender de la red al transcribir
RUN /app/.venv/bin/homr --init

# Etapa final ligera para ejecución
FROM python:3.12-slim-bookworm AS runner

WORKDIR /app

# libgl1 y libglib2.0-0: OpenCV (dependencia de HOMR) los necesita para importarse
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# En producción: aplicar migraciones Alembic y arrancar FastAPI (#6)
CMD ["sh", "-c", "alembic -c packages/persistence/alembic.ini upgrade head && uvicorn cadenza.api.main:create_default_app --factory --host 0.0.0.0 --port 8000"]
