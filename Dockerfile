# Dockerfile de producción para el plano online de Cadenza (#6, ADR-0015, ADR-0018)
# Las dos etapas usan la misma imagen base fijada: el entorno virtual del builder enlaza al
# intérprete de /usr/local/bin y debe encontrar el mismo en la etapa final (#135).
FROM python:3.12.15-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

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

# Descarga los pesos de HOMR en la imagen para no depender de la red al transcribir.
# También descarga los de RapidOCR, aunque el adaptador desactiva el OCR de título.
RUN /app/.venv/bin/homr --init

# Etapa final ligera para ejecución
FROM python:3.12.15-slim-bookworm AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios (D57, #192). El UID y el GID son fijos: el procedimiento que da los
# volúmenes de artefactos existentes a este usuario los nombra (operacion_backend.md §2.2).
RUN groupadd --system --gid 10001 cadenza \
    && useradd --system --uid 10001 --gid cadenza --create-home --home-dir /home/cadenza \
        --shell /usr/sbin/nologin cadenza

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

# Falla al construir si la API o HOMR no se pueden importar en la imagen final (#135)
RUN python -c "import cadenza.api.main, homr.main, cv2, onnxruntime"

# El código de la imagen es de root y solo se lee. Los paquetes del workspace se instalan en
# modo editable y uv no los compila: se compilan aquí, porque el usuario de la API no puede
# escribir su caché de bytecode. La carpeta de artefactos es suya: un volumen nuevo la hereda
# con este dueño.
RUN python -m compileall -q /app/apps /app/packages \
    && mkdir -p /app/data/artifacts \
    && chown -R cadenza:cadenza /app/data

USER cadenza

EXPOSE 8000

# En producción: aplicar migraciones Alembic y arrancar FastAPI (#6)
# Detrás de un proxy (ADR-0023), uvicorn toma la IP del cliente de X-Forwarded-For solo si la
# petición llega de CADENZA_FORWARDED_ALLOW_IPS (por defecto, solo localhost).
CMD ["sh", "-c", "alembic -c packages/persistence/alembic.ini upgrade head && uvicorn cadenza.api.main:create_default_app --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${CADENZA_FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
