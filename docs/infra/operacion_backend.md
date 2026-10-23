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
| `CADENZA_OMR_USE_GPU` | `bool` | `false` | Activa aceleración GPU (CUDA) para la inferencia de HOMR, único motor OMR (ADR-0018), en el plano online. |
| `CADENZA_ARTIFACTS_DIR` | `path` | `./data/artifacts` | Ruta raíz para el almacenamiento de archivos del `ArtifactStore`. |
| `CADENZA_AUTO_CREATE_SCHEMA` | `bool` | `false` | Si es `true`, crea DDL al arrancar (solo tests/dev). En producción usar Alembic. |
| `CADENZA_CORS_ORIGINS` | `list[str]` | `*` | Orígenes permitidos para peticiones cruzadas: `*` o `esquema://host[:puerto]` (sin ruta ni barra final), uno o varios separados por comas o en una lista JSON. `*` va solo y no envía credenciales; `[]` desactiva CORS (con Docker Compose, un valor vacío se convierte en `*`). Un valor mal escrito impide arrancar la API. |
| `CADENZA_LOGIN_RATE_LIMIT_MAX_ATTEMPTS` | `int` | `5` | Máximo de fallos antes de bloquear temporalmente intentos en `/auth/login`. |
| `CADENZA_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `int` | `300` | Ventana temporal en segundos (5 min) para la protección contra fuerza bruta. |
| `CADENZA_REGISTRATION_ENABLED` | `bool` | `false` | Abre `POST /auth/register` ([ADR-0022](../adr/ADR-0022-registro-de-cuentas-con-activacion.md)): la cuenta nace inactiva y marcada como autorregistrada hasta que un investigador la activa. Apagado, la ruta responde 404 sea cual sea el cuerpo. Encendido exige `CADENZA_CORS_ORIGINS` sin `*` (si no, la API no arranca) y, para que el límite cuente por visitante, un proxy de confianza que dé la IP real ([#156](https://github.com/sebdavid3/Cadenza/issues/156)): sin él, todas las peticiones llegan con la IP del proxy y el límite es uno solo para todo el servicio. |
| `CADENZA_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS` | `int` | `5` | Intentos de registro por IP (red /64 en IPv6) en la ventana, como mínimo 1. Cuentan los que llegan a procesarse, también los que acaban en 409 (nombre ocupado); un cuerpo que no supera el esquema (422) no cuenta porque no toca la base de datos. |
| `CADENZA_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS` | `int` | `3600` | Ventana en segundos del límite de registros por IP, como mínimo 1. |
| `CADENZA_REGISTRATION_MAX_PENDING` | `int` | `50` | Con tantas cuentas autorregistradas pendientes de activación, el registro responde 503 hasta que un investigador las revise. |
| `CADENZA_TRANSCRIBE_MAX_CONCURRENCY` | `int` | `2` | Transcripciones que la API admite a la vez, de 1 a 8, con un hilo cada una ([ADR-0024](../adr/ADR-0024-transcripciones-simultaneas.md)). HOMR no es seguro entre hilos y calcula de una en una; el resto espera su turno. Una petición sin hueco espera hasta 10 s y luego responde 503 con `Retry-After: 10`. Si el cliente se va a mitad, la transcripción termina, se guarda y entonces libera su hueco. |
| `CADENZA_DISABLE_POWER_THROTTLING` | `bool` | `true` | Desactiva la limitación de energía (EcoQoS) del proceso en Windows (#106). |
| `CADENZA_FORWARDED_ALLOW_IPS` | `str` | `127.0.0.1` | Solo en la imagen Docker (el `CMD` del `Dockerfile`, no la API): direcciones o redes desde las que uvicorn acepta `X-Forwarded-For` y `X-Forwarded-Proto` (`--forwarded-allow-ips`). En `docker-compose.prod.yml` es la IP fija del servicio `web`, `10.77.0.10` ([ADR-0023](../adr/ADR-0023-despliegue-publico-con-tailscale-funnel.md)). |

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

La imagen de la API (`Dockerfile`) instala el paquete `cadenza-api` con el extra `homr` desde `uv.lock` y descarga los pesos de HOMR al construirse (`homr --init`): transcribe en CPU sin acceso a la red. El build falla si la API, HOMR u OpenCV no se pueden importar, y el job `docker` de la CI lo construye en cada PR. HOMR es el único motor OMR ([ADR-0018](../adr/ADR-0018-homr-como-unico-motor-omr.md)); la imagen no incluye `onnxruntime-gpu`. El primer usuario se crea dentro del contenedor:

```bash
docker exec -it cadenza-api python -m cadenza.api.cli create-investigator --username <usuario>
```

Sin `--password`, la CLI pide la contraseña sin eco y dos veces; pasarla como argumento la deja en el historial del shell y en la lista de procesos.

Verificado el 2026-10-20 con `docker compose up --build`: migraciones 0001–0011 aplicadas sobre PostgreSQL 16, `GET /health` con `"omr_engine": "homr"` y `POST /transcribe` = 201 con una imagen de PrIMuS ([#135](https://github.com/sebdavid3/Cadenza/issues/135)).

### 2.2 Despliegue público (`docker-compose.prod.yml`)

El despliegue público ([ADR-0023](../adr/ADR-0023-despliegue-publico-con-tailscale-funnel.md), [#156](https://github.com/sebdavid3/Cadenza/issues/156)) usa un compose propio (proyecto `cadenza-prod`), independiente del de desarrollo:

| Servicio | Imagen | Puertos | Función |
|---|---|---|---|
| `postgres` | `postgres:16.15-alpine3.24` | ninguno | Base de datos, volumen `postgres_data` |
| `api` | `Dockerfile` (`cadenza-api:prod`) | ninguno | FastAPI con HOMR en CPU; aplica las migraciones al arrancar; volumen `artifacts_data`; tope de memoria de 3 GiB |
| `web` | `Dockerfile.web` (`cadenza-web:prod`) | `127.0.0.1:${CADENZA_WEB_PORT:-8380}` | Nginx sin privilegios: sirve `apps/web/dist` (con `index.html` para las rutas de la interfaz) y reenvía `/api/*` a `api:8000` quitando el prefijo (`deploy/nginx/`) |

Puesta en marcha en el servidor:

```bash
cp deploy/.env.example .env
chmod 600 .env
# Rellenar CADENZA_AUTH_SECRET_KEY y CADENZA_POSTGRES_PASSWORD con openssl rand -hex 32
docker compose -f docker-compose.prod.yml up -d --build
sudo tailscale funnel --bg 8380
```

- **Funnel en modo proxy HTTP**, como en el último comando: termina TLS y reenvía a `http://127.0.0.1:8380` añadiendo `X-Forwarded-For`. Los modos TCP (`--tcp`, `--tls-terminated-tcp`) no se usan: no añaden la cabecera, todos los visitantes compartirían una IP y cualquiera podría inventarse la suya.
- **IP real.** La red de Compose tiene una subred fija (`10.77.0.0/24`): lo que Funnel reenvía a `127.0.0.1` entra por la pasarela `10.77.0.1`, y `web` tiene la dirección `10.77.0.10` (las dinámicas salen de `10.77.0.128/25`, así que ningún otro contenedor puede ocuparla). Nginx cree `X-Forwarded-For` solo si viene de la pasarela, toma su última dirección y la reenvía a la API **sustituyendo** la cabecera; uvicorn la acepta solo de `web` (`CADENZA_FORWARDED_ALLOW_IPS`, `--proxy-headers`). Así, los límites del login y del registro cuentan por visitante. Si se cambia la subred, hay que cambiar también `deploy/nginx/cadenza.conf`.
- **Límites en Nginx**, además de los de la API y por visitante (la IPv4, o la red /64 de una IPv6, como en la API): 10 peticiones por minuto a `/api/auth/login` y otras 10 a `/api/auth/register`, con ráfagas de 10 y cuerpos de hasta 16 KB, y 4 transcripciones abiertas a la vez; por encima, 429. Las rutas con caracteres de control responden 400 antes de elegir la `location`: `/api/auth/login%0A` esquivaría el límite exacto y la API la atendería como su login. Varias personas tras una misma IP (una sala, un campus) comparten estos límites.
- **Cabeceras**: política de seguridad de contenido (`script-src 'self'`; `style-src` con `'unsafe-inline'` porque OSMD dibuja con atributos `style`), `nosniff`, `X-Frame-Options: DENY` y `Referrer-Policy: same-origin`; gzip para JavaScript, CSS, JSON y SVG. `/api/docs`, `/api/redoc` y `/api/openapi.json` responden 404: el contrato está en el repositorio.
- **Contenedores**: registros con rotación (5 archivos de 10 MB), `no-new-privileges` en los tres y, en `api` y `web`, sin capacidades de Linux. La interfaz no espera a que la API esté sana: con la API caída, `/` sigue respondiendo y `/api/*` da 502.
- **CORS** limitado a `CADENZA_PUBLIC_ORIGIN`; el navegador llama a la API en el mismo origen, bajo `/api`.
- **Registro**: `CADENZA_REGISTRATION_ENABLED` enciende la ruta de la API y, como argumento del build de `web`, los enlaces de la interfaz. Solo admite `true` o `false`: la API aceptaría también `1`, `yes` u `on`, pero el build compara con `true` y dejaría ocultos los enlaces.
- **Secretos** solo en el `.env` del servidor (`chmod 600`), a partir de `deploy/.env.example`; nunca salen del servidor. `docker compose config` imprime el compose con los secretos ya sustituidos: no se pega su salida en ningún sitio.

Comprobado el 2026-10-23 en el servidor del despliegue (i5-10300H, 7,1 GiB de RAM), con proyectos desechables en `127.0.0.1:18380` que se retiraron después; las cifras son de la última prueba, con esta configuración:
- Servicios en `healthy`, con las imágenes construidas en el servidor (`up -d --build`: 85 s). Las direcciones dinámicas de la red salen de la mitad alta (`postgres` en `10.77.0.128`, `api` en `10.77.0.129`) y `web` tiene `10.77.0.10`.
- `/`, `/entrar`, `/registro` y `/sesiones/abc` responden 200 con `index.html`; `/api/health` y `/api/version`, 200 con `device: cpu`; `/api/docs`, `/api/redoc` y `/api/openapi.json`, 404. Con la API parada, `/` da 200 y `/api/health`, 502.
- En el host solo escucha `127.0.0.1:18380`; 5432, 8000 y 18380 no responden desde la IP de Tailscale.
- IP real: sin cabecera, Nginx ve la pasarela `10.77.0.1`; con `X-Forwarded-For: 198.51.100.4, 203.0.113.9` desde la pasarela, `203.0.113.9`; uvicorn ve la IP que le pasa `web`, y una `X-Forwarded-For` enviada desde otro contenedor de la red no se cree (ve `10.77.0.128`, la IP de ese contenedor).
- Con un límite de 3 registros, la misma IP da 201, 201, 201 y 429, y otra IP vuelve a dar 201. 25 intentos de acceso seguidos desde una IP, con usuarios distintos: 11 respuestas 401 y 14 respuestas 429 de Nginx; agotado el acceso, el registro desde esa IP sigue dando 201 (zonas aparte). 11 accesos desde `2001:db8:1:2::1` dan 401, y el siguiente desde otra dirección de la misma /64 da 429; desde otra /64, 401.
- `/api/auth/login%0A`, `/api/auth/register%0A`, `/api/transcribe%0A`, `/api/docs%0A` y `/sesiones/abc%09` responden 400; un acceso con un cuerpo de 20 KB, 413.
- `POST /transcribe` con un incipit de PrIMuS en CPU: 201 en 2,33 s. Cinco a la vez desde una IP: un 429 de Nginx y cuatro que llegan a la API, con un pico de memoria de 1968 MiB y sin que el kernel la mate. Esas transcripciones simultáneas destaparon dos fallos anteriores a este despliegue, que van aparte. HOMR no es seguro entre hilos: con cuatro imágenes distintas a la vez, varias respondían 422 con errores internos de ONNX Runtime ([#165](https://github.com/sebdavid3/Cadenza/issues/165)). Y la API confirmaba la transacción después de enviar la respuesta: enviar la misma imagen dos veces seguidas dio un 500 por clave duplicada ([#166](https://github.com/sebdavid3/Cadenza/issues/166)).
- Tras corregir los dos ([#165](https://github.com/sebdavid3/Cadenza/issues/165), [#166](https://github.com/sebdavid3/Cadenza/issues/166), [ADR-0024](../adr/ADR-0024-transcripciones-simultaneas.md)), con dos huecos de transcripción: la misma imagen dos veces seguidas da 201 y 201. Tres rondas de 4 transcripciones simultáneas con imágenes distintas dan 201 en todas, servidas de una en una (de 1,7 a 7,7 s). Una ronda de 8 da siete 201 y un 503 tras esperar 10 s. Ningún 422 ni 500, un pico de memoria de la API de 1227 MiB y ningún reinicio.
- En Chrome sin interfaz por un túnel SSH (1440 y 390 px): landing, registro, acceso, transcripción, vista de una sesión con cuatro compases marcados y cuentas, sin ninguna violación de la política de seguridad de contenido; un `<script>` en línea inyectado como control sí queda bloqueado.

La primera cuenta de investigador se crea dentro del contenedor; sin `--password`, la CLI la pide sin eco y dos veces, para que no quede en el historial del shell:

```bash
docker compose -f docker-compose.prod.yml exec api python -m cadenza.api.cli create-investigator --username <usuario>
```

### 2.3 Ejecución del plano offline con GPU (perfil batch)

Para correr jobs de active learning, reentrenamientos con PyTorch o experimentos con aceleración NVIDIA CUDA:

```bash
docker compose --profile batch run --rm ml-batch --help
docker compose --profile batch run --rm ml-batch run --config configs/learning/default.json
```

> [!WARNING]
> Hoy la imagen `Dockerfile.ml-cuda` no se construye (deuda D53): pide `--extra torch --extra metrics` a la raíz del workspace, que no define extras (también en su alternativa `|| uv sync ...`), fija uv 0.5.21, anterior al formato del lockfile, y copia el `pyproject.toml` de `apps/api`, miembro del workspace, pero no su código. Su arreglo depende del alcance del ajuste fino real del modelo ([#103](https://github.com/sebdavid3/Cadenza/issues/103)).

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
  "omr_engine": "homr",
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

Asimismo, el middleware de observabilidad asigna a cada petición la cabecera `X-Request-ID` (generada automáticamente o propagada desde el cliente; en el despliegue público la fija Nginx con su `$request_id` y sustituye la del cliente, §2.2) y emite un registro estructurado al completar cada solicitud:

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
