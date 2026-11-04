# Dockerfile de producción para el plano online de Cadenza (#6, ADR-0015, ADR-0018)
# Las etapas usan la misma imagen base fijada: el entorno virtual de deps enlaza al intérprete
# de /usr/local/bin y debe encontrar el mismo en la etapa final (#135).
#
# Las dependencias y el código van en etapas y capas aparte (#205): un cambio de código no
# reinstala las dependencias, no vuelve a descargar los pesos de HOMR ni copia otra vez a la
# etapa final el entorno virtual, de 1,2 GB. Cada reconstrucción deja así en la caché unos
# megas en lugar de unos 2,5 GB.
FROM python:3.12.15-slim-bookworm AS deps

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never

# `uv sync --frozen` necesita el pyproject.toml de todos los miembros del workspace.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/
COPY packages/application/pyproject.toml packages/application/
COPY packages/domain/pyproject.toml packages/domain/
COPY packages/interchange/pyproject.toml packages/interchange/
COPY packages/learning/pyproject.toml packages/learning/
COPY packages/omr/pyproject.toml packages/omr/
COPY packages/persistence/pyproject.toml packages/persistence/
COPY packages/validation/pyproject.toml packages/validation/

# La raíz del workspace es un proyecto virtual sin dependencias propias (los paquetes
# solo figuran en el grupo dev): se instalan las dependencias del paquete de la API con el
# extra de HOMR, el único motor OMR (#135), sin los paquetes del workspace.
RUN uv sync --frozen --no-dev --package cadenza-api --extra homr --no-install-workspace

# Descarga los pesos de HOMR en la imagen para no depender de la red al transcribir.
# También descarga los de RapidOCR, aunque el adaptador desactiva el OCR de título.
RUN /app/.venv/bin/homr --init

# El código y, con él, los paquetes del workspace, en modo editable.
FROM deps AS builder

COPY apps/api/ apps/api/
COPY packages/ packages/
RUN uv sync --frozen --no-dev --package cadenza-api --extra homr

# Lo único que esa instalación añade al entorno virtual: los dist-info de los paquetes del
# workspace y los .pth que apuntan a su código. Su RECORD cambia con cada construcción, así que
# la etapa final los copia aparte del resto del entorno.
RUN mkdir /workspace-site \
    && cp -a .venv/lib/python3.12/site-packages/cadenza_*.dist-info \
        .venv/lib/python3.12/site-packages/_editable_impl_cadenza_*.pth /workspace-site/

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

# El entorno virtual de las dependencias se reutiliza mientras no cambien; los paquetes del
# workspace y el código, que cambian con cada versión, van en capas pequeñas aparte (#205).
COPY --from=deps /app/.venv /app/.venv
COPY --from=builder /workspace-site/ /app/.venv/lib/python3.12/site-packages/
COPY --from=builder /app/apps /app/apps
COPY --from=builder /app/packages /app/packages

ENV PATH="/app/.venv/bin:$PATH"

# Falla al construir si la API o HOMR no se pueden importar en la imagen final (#135)
RUN python -c "import cadenza.api.main, homr.main, cv2, onnxruntime"

# Falla también si falta algún archivo de los paquetes del workspace: de su instalación solo se
# copian los dist-info y los .pth, y un script de consola, por ejemplo, se quedaría atrás (#205).
# Lee el RECORD directamente: desde Python 3.12, Distribution.files omite lo que no existe.
RUN python -c "import csv, importlib.metadata as md; \
missing = [p for d in md.distributions() if (d.metadata['Name'] or '').startswith('cadenza-') for p, *_ in csv.reader((d.read_text('RECORD') or '').splitlines()) if not d.locate_file(p).exists()]; \
assert not missing, missing"

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
