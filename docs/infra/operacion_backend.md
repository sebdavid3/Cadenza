# Guía de Operación y Despliegue del Backend — Cadenza

> **Referencia de Arquitectura:** [ADR-0015](../adr/ADR-0015-operacion-y-despliegue-del-backend.md) · [ARCHITECTURE.md](../ARCHITECTURE.md) §3 y §4 · Issue #40 (Deuda D44)

---

## 1. Variables de entorno de configuración

El backend se configura siguiendo los principios de la metodología *12-Factor App* mediante variables de entorno con prefijo `CADENZA_`:

| Variable | Tipo | Valor por defecto | Descripción |
|---|---|---|---|
| `CADENZA_DATABASE_URL` | `str` | `sqlite+pysqlite:///./cadenza.db` | URL de conexión SQLAlchemy (SQLite o PostgreSQL). |
| `CADENZA_AUTH_SECRET_KEY` | `str` | *(vacío)* | Clave secreta criptográfica (mínimo 32 bytes) para firma de tokens JWT. |
| `CADENZA_AUTH_TOKEN_EXPIRE_MINUTES` | `int` | `30` | Minutos de expiración para tokens de acceso. |
| `CADENZA_OMR_ENGINE` | `enum` | `fake` | Motor OMR (`fake`, `homr`, `oemer`). |
| `CADENZA_OMR_USE_GPU` | `bool` | `false` | Activa aceleración GPU (CUDA) para inferencia OMR en el plano online. |
| `CADENZA_ARTIFACTS_DIR` | `path` | `./data/artifacts` | Ruta raíz para el almacenamiento de archivos del `ArtifactStore`. |
| `CADENZA_AUTO_CREATE_SCHEMA` | `bool` | `false` | Si es `true`, crea DDL al arrancar (solo tests/dev). En producción usar Alembic. |
| `CADENZA_CORS_ORIGINS` | `list[str]` | `*` | Orígenes permitidos para peticiones cruzadas: `*` o `esquema://host[:puerto]` (sin ruta ni barra final), uno o varios separados por comas o en una lista JSON. `*` va solo y no envía credenciales; `[]` desactiva CORS (con Docker Compose, un valor vacío se convierte en `*`). Un valor mal escrito impide arrancar la API. |
| `CADENZA_LOGIN_RATE_LIMIT_MAX_ATTEMPTS` | `int` | `5` | Máximo de fallos antes de bloquear temporalmente intentos en `/auth/login`. |
| `CADENZA_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `int` | `300` | Ventana temporal en segundos (5 min) para la protección contra fuerza bruta. |
| `CADENZA_DISABLE_POWER_THROTTLING` | `bool` | `true` | Desactiva la limitación de energía (EcoQoS) del proceso en Windows (#106). |

---

## 2. Despliegue con Docker Compose

El archivo `docker-compose.yml` orquesta los servicios de producción y demostración.

### 2.1 Puesta en marcha del plano online

```bash
# 1. Configurar variables seguras
cp .env.example .env
# Editar .env con contraseñas seguras y una clave CADENZA_AUTH_SECRET_KEY aleatoria

# 2. Levantar servicios
docker compose up -d --build

# 3. Verificar estado de los contenedores y healthchecks
docker compose ps
```

El servicio `api` cuenta con un `healthcheck` automatizado que invoca periódicamente `GET /health`.

### 2.2 Ejecución del plano offline con GPU (perfil batch)

Para correr jobs de active learning, reentrenamientos con PyTorch o experimentos con aceleración NVIDIA CUDA:

```bash
docker compose --profile batch run --rm ml-batch --help
docker compose --profile batch run --rm ml-batch run --config configs/learning/default.json
```

---

## 3. Sondas de Salud y Observabilidad

### 3.1 Endpoint `GET /health`

Permite a orquestadores (Kubernetes, AWS ECS, Docker Compose) comprobar la salud del servicio:

```bash
curl -i http://localhost:8000/health
```

**Respuesta HTTP 200 (Healthy):**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "artifact_store": "accessible",
  "omr_engine": "fake",
  "device": "cpu"
}
```

En caso de fallo en la base de datos o en el almacenamiento de artefactos, el endpoint responde con **HTTP 503 Service Unavailable** y `"status": "unhealthy"`.

### 3.2 Trazabilidad con `X-Request-ID` y Logs Estructurados

La API configura sus manejadores de registro durante el ciclo de vida de la aplicación (`configure_logging` en `cadenza.api.main`). Si el registrador raíz `cadenza` no tiene manejadores asignados (como ocurre en el arranque estándar con `uvicorn cadenza.api.main:create_default_app --factory`), se asocia un `StreamHandler(sys.stderr)` con el formateador por defecto de Uvicorn (`DefaultFormatter`), asegurando que todos los registros de `cadenza.*` sean visibles en consola sin duplicar salidas ni pisar configuraciones preexistentes.

Al iniciar, la API emite el estado de la renuncia a la limitación de energía (EcoQoS en Windows, implementada en `cadenza.omr.power`):

```text
INFO:     power_throttling_disabled requested=True applied=True platform=win32
```

Asimismo, el middleware de observabilidad asigna a cada petición la cabecera `X-Request-ID` (generada automáticamente o propagada desde el cliente) y emite un registro estructurado al completar cada solicitud:

```text
INFO:     request_completed method=GET path=/health status=200 duration_ms=4.23 request_id=74207509005b4c9ba98271fdb99356e4 session_id=-
INFO:     request_completed method=POST path=/auth/login status=200 duration_ms=56.87 request_id=ba9cdbae5089458788b0b056d900d584 session_id=-
INFO:     request_completed method=POST path=/transcribe status=201 duration_ms=15.53 request_id=ceb7d7b0daa740d5a1d095a2ab1a1023 session_id=-
INFO:     request_completed method=GET path=/sessions/e40a68a3-36d3-410b-91af-dc9685f10ac3 status=200 duration_ms=9.19 request_id=67e933c55eb742068c55e4f0b7502c65 session_id=e40a68a3-36d3-410b-91af-dc9685f10ac3
```

---

## 4. Copias de Seguridad y Recuperación ante Desastres

El script `scripts/backup_restore.py` permite crear snapshots atómicos de la base de datos y de todos los artefactos (`ArtifactStore`), verificando la integridad de cada archivo mediante SHA-256.

### 4.1 Crear una copia de seguridad

```bash
uv run python scripts/backup_restore.py backup --output backup-2026-10-08.tar.gz
```

### 4.2 Verificar la integridad de una copia

```bash
uv run python scripts/backup_restore.py verify --archive backup-2026-10-08.tar.gz
```

### 4.3 Restaurar una copia de seguridad

```bash
uv run python scripts/backup_restore.py restore --archive backup-2026-10-08.tar.gz --force
```
