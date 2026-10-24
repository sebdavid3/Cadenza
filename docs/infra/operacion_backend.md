# Guía de Operación y Despliegue del Backend — Cadenza

> **Referencia de Arquitectura:** [ADR-0015](../adr/ADR-0015-operacion-y-despliegue-del-backend.md) · [ARCHITECTURE.md](../ARCHITECTURE.md) §3 y §4 · Issue #40 (Deuda D44)

---

## 1. Variables de entorno de configuración

El backend se configura siguiendo los principios de la metodología *12-Factor App* mediante variables de entorno con prefijo `CADENZA_`:

| Variable | Tipo | Valor por defecto | Descripción |
|---|---|---|---|
| `CADENZA_DATABASE_URL` | `str` | `sqlite+pysqlite:///./cadenza.db` | URL de conexión SQLAlchemy (SQLite o PostgreSQL). |
| `CADENZA_AUTH_SECRET_KEY` | `str` | *(vacío)* | Clave secreta para la firma de los tokens JWT, de 32 bytes como mínimo ([#193](https://github.com/sebdavid3/Cadenza/issues/193)). Con una más corta, la API no arranca y el error dice su longitud, nunca la clave; vacía, tampoco arranca. |
| `CADENZA_AUTH_TOKEN_EXPIRE_MINUTES` | `int` | `30` | Minutos de expiración para tokens de acceso. |
| `CADENZA_OMR_USE_GPU` | `bool` | `false` | Activa aceleración GPU (CUDA) para la inferencia de HOMR, único motor OMR (ADR-0018), en el plano online. |
| `CADENZA_ARTIFACTS_DIR` | `path` | `./data/artifacts` | Ruta raíz para el almacenamiento de archivos del `ArtifactStore`. |
| `CADENZA_AUTO_CREATE_SCHEMA` | `bool` | `false` | Si es `true`, crea DDL al arrancar (solo tests/dev). En producción usar Alembic. |
| `CADENZA_CORS_ORIGINS` | `list[str]` | `*` | Orígenes permitidos para peticiones cruzadas: `*` o `esquema://host[:puerto]` (sin ruta ni barra final), uno o varios separados por comas o en una lista JSON. `*` va solo y no envía credenciales; `[]` desactiva CORS (con Docker Compose, un valor vacío se convierte en `*`). Un valor mal escrito impide arrancar la API. |
| `CADENZA_LOGIN_RATE_LIMIT_MAX_ATTEMPTS` | `int` | `5` | Máximo de fallos antes de bloquear temporalmente intentos en `/auth/login`. |
| `CADENZA_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `int` | `300` | Ventana temporal en segundos (5 min) para la protección contra fuerza bruta. |
| `CADENZA_REGISTRATION_ENABLED` | `bool` | `false` | Abre `POST /auth/register` ([ADR-0022](../adr/ADR-0022-registro-de-cuentas-con-activacion.md), [ADR-0025](../adr/ADR-0025-registro-abierto-sin-aprobacion.md)): la cuenta nace activa y marcada como autorregistrada, y un investigador puede desactivarla. Apagado, la ruta responde 404 sea cual sea el cuerpo. Encendido exige `CADENZA_CORS_ORIGINS` sin `*` (si no, la API no arranca) y, para que el límite cuente por visitante, un proxy de confianza que dé la IP real ([#156](https://github.com/sebdavid3/Cadenza/issues/156)): sin él, todas las peticiones llegan con la IP del proxy y el límite es uno solo para todo el servicio. |
| `CADENZA_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS` | `int` | `5` | Intentos de registro por IP (red /64 en IPv6) en la ventana, como mínimo 1. Cuentan los que llegan a procesarse, también los que acaban en 409 (nombre ocupado); un cuerpo que no supera el esquema (422) no cuenta porque no toca la base de datos. |
| `CADENZA_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS` | `int` | `3600` | Ventana en segundos del límite de registros por IP, como mínimo 1. |
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
| `api` | `Dockerfile` (`cadenza-api:prod`) | ninguno | FastAPI con HOMR en CPU, con el usuario `cadenza` (UID 10001), sin root; aplica las migraciones al arrancar; volumen `artifacts_data`; tope de memoria de 3 GiB |
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
- **Contenedores**: registros con rotación (5 archivos de 10 MB), `no-new-privileges` en los tres y, en `api` y `web`, sin capacidades de Linux. Ni la API ni Nginx corren como root; la API, con el usuario `cadenza` ([ADR-0029](../adr/ADR-0029-api-con-usuario-sin-privilegios.md)). La interfaz no espera a que la API esté sana: con la API caída, `/` sigue respondiendo y `/api/*` da 502.
- **CORS** limitado a `CADENZA_PUBLIC_ORIGIN`; el navegador llama a la API en el mismo origen, bajo `/api`.
- **Registro** abierto, sin aprobación (ADR-0025): `CADENZA_REGISTRATION_ENABLED` enciende la ruta de la API y, como argumento del build de `web`, los enlaces de la interfaz. Solo admite `true` o `false`: la API aceptaría también `1`, `yes` u `on`, pero el build compara con `true` y dejaría ocultos los enlaces.
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

#### Usuario de la API y volúmenes anteriores ([#192](https://github.com/sebdavid3/Cadenza/issues/192), [ADR-0029](../adr/ADR-0029-api-con-usuario-sin-privilegios.md))

La API corre con el usuario `cadenza` (UID y GID 10001), dueño de `/app/data/artifacts`; un volumen nuevo hereda ese dueño si lo monta primero la API. Un volumen creado con una imagen anterior a #192 es de root: la API lo lee, pero no escribe en él, y `/health` responde 503 con `artifact_store: "error"` y deja en el registro «la API no puede escribir en /app/data/artifacts». Se migra una sola vez, con la imagen nueva construida y antes de arrancarla:

```bash
DC="docker compose -f docker-compose.prod.yml --env-file .env"

# Copia, código nuevo e imágenes nuevas, también la de copias
$DC --profile backup run --rm backup backup --output /backups/cadenza-$(date +%F-%H%M).tar.gz
git pull --ff-only
$DC build api web
$DC --profile backup build backup
docker run --rm --entrypoint id cadenza-api:prod -u   # ha de dar 10001: la imagen es la nueva

# Migración: con la API parada, el volumen pasa al usuario de la API
$DC stop api
docker volume inspect cadenza-prod_artifacts_data >/dev/null \
  && docker run --rm --user 0 --entrypoint chown -v cadenza-prod_artifacts_data:/app/data/artifacts cadenza-api:prod -R 10001:10001 /app/data/artifacts
$DC up -d
```

- **Nombre del volumen.** Es `<proyecto>_artifacts_data`: con el compose de producción, `cadenza-prod_artifacts_data`, y con el de desarrollo, `cadenza_artifacts_data` (`docker volume ls`). `docker volume inspect` evita que un nombre mal escrito cree un volumen nuevo y la migración parezca hecha.
- **Contenedor de la migración.** Es desechable y corre como root, sin las restricciones del servicio: `chown` necesita la capacidad `CHOWN`, que el servicio no tiene.
- **Orden.** Si la API ya arrancó con la imagen nueva (por ejemplo, con `up -d --build`), la migración se puede hacer igual después: sin permiso, la API no escribe nada, y `/health` se recupera sin reiniciarla.
- **Restauraciones.** La de §4.2 da lo restaurado al usuario de la API (`CADENZA_ARTIFACTS_OWNER`), también si crea ella el volumen: después de restaurar no hace falta repetir la migración. Con una imagen de copias anterior a #192 sí haría falta, y `/health` no lo vería: solo mira la carpeta de artefactos y `sha256`, no las de prefijo.

Comprobado el 2026-10-23 en el servidor del despliegue, con una imagen de prueba, volúmenes y contenedores desechables que se retiraron después, y las restricciones del despliegue (`cap_drop: ALL`, `no-new-privileges`):
- HOMR transcribe sin root un incipit de PrIMuS (22 notas) y el íncipit de la CI (sus 14 alturas). Solo escribe en `/tmp` y en `~/.cache` (el identificador de dispositivo de ONNX Runtime); los pesos de la imagen no se tocan.
- Con un volumen de root sin migrar, la API lee los artefactos y no puede escribir (`Permission denied`); `/health`, 503. Tras la migración, escribe y crea carpetas, y `/health` da 200.
- Una copia restaurada como root en un volumen de la API deja los artefactos y sus carpetas con UID 10001, y la API escribe en ellas.
- Tras la revisión, en un volumen que crea la propia restauración, con `CADENZA_ARTIFACTS_OWNER=10001:10001`: la carpeta de artefactos, las de prefijo y el artefacto quedan con UID 10001.

#### Despliegue en el homelab ([#157](https://github.com/sebdavid3/Cadenza/issues/157), 2026-10-23)

Cadenza está publicada en **https://r2d2.tailcacb19.ts.net**, desde `/opt/docker/cadenza` en el servidor `r2d2`, un clon de la rama `dev`:
- `.env` generado en el servidor con secretos aleatorios de 64 caracteres y permisos 600. Los secretos no han salido de allí.
- Copias en `/opt/docker/cadenza/backups`, con permisos 700, una al día por cron (§4.3).
- Funnel en modo proxy HTTP (`sudo tailscale funnel --bg 8380`), activado por el responsable.

Procedimientos, en el servidor y dentro de `/opt/docker/cadenza`:

```bash
DC="docker compose -f docker-compose.prod.yml --env-file .env"

# Actualizar: copia antes, código nuevo y reconstrucción. La API aplica las migraciones al arrancar.
$DC --profile backup run --rm backup backup --output /backups/cadenza-$(date +%F-%H%M).tar.gz
git pull --ff-only
$DC up -d --build
$DC --profile backup build backup   # la imagen de copias no se reconstruye sola con «up»

# Parar y volver a arrancar: los volúmenes, y con ellos los datos, se conservan
$DC down
$DC up -d

# Retirar de internet sin parar los servicios, y volver a publicar
sudo tailscale funnel --https=443 off
sudo tailscale funnel --bg 8380
```

- La primera actualización a una versión con #192 necesita además, una sola vez, la migración del volumen de artefactos (sección anterior).
- Para restaurar una copia, ver la §4.2.
- `down -v` borra los volúmenes con la base de datos y los artefactos: no se usa.
- Una prueba desechable de esta configuración en el mismo servidor necesita otra subred, porque dos redes con `10.77.0.0/24` no pueden coexistir.

Comprobado al publicar, desde fuera del tailnet. Se usó otra IP pública, conectando a la IP de Funnel que devuelve un DNS público:

| Comprobación | Resultado |
|---|---|
| Certificado | Let's Encrypt para `r2d2.tailcacb19.ts.net`, válido hasta el 2 de enero de 2027 |
| `/`, `/entrar`, `/registro`, `/sesiones/abc`, `/api/health`, `/api/version` | 200, de 0,86 a 2,61 s; `/api/health` con la base de datos conectada y `device: cpu` |
| `/api/docs`, `/api/openapi.json` | 404 |
| `/api/auth/login%0A` | 400 |
| Cabeceras | CSP, `X-Frame-Options`, `nosniff` y `Referrer-Policy` presentes |
| `X-Forwarded-For` inventada a través de Funnel | Nginx y uvicorn registran la IP pública real del cliente: Funnel añade la cabecera como se esperaba ([ADR-0023](../adr/ADR-0023-despliegue-publico-con-tailscale-funnel.md)) |
| Flujo por la API | registro 201 (1,52 s), entrada 200, transcripción de un incipit de PrIMuS 201 (3,44 s); sesión, hallazgos, MusicXML e imagen 200 |
| Chrome sin interfaz por la URL pública (1440 y 390 px) | landing, registro, entrada, transcripción (2,27 s) y vista de la sesión, sin violaciones de la política de seguridad de contenido |
| Puertos | desde la IP de Tailscale, 5432, 8000 y 8380 no responden; en el host solo escucha `127.0.0.1:8380` |
| Otros servicios | Immich y los puertos 2283, 7103, 7104 y 8090 siguen igual |
| Memoria en reposo | API 724 MiB, PostgreSQL 62 MiB, web 9 MiB |
| Copias | la primera copia (1 s, `verify` válida) se restauró en una base aparte con los mismos recuentos que producción; la base de prueba se borró después |

El primer acceso público, mientras Funnel obtenía el certificado, cortó el handshake TLS. Unos minutos después ya respondía.

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

En caso de fallo en la base de datos o en el almacenamiento de artefactos, el endpoint responde con **HTTP 503 Service Unavailable** y `"status": "unhealthy"`. El almacenamiento falla también si la API no puede escribir en su carpeta o en su `sha256`, como un volumen de root sin migrar (§2.2, [ADR-0029](../adr/ADR-0029-api-con-usuario-sin-privilegios.md)). Antes de #192, en producción no se comprobaba esa carpeta: el almacén no se inyecta y `/health` solo miraba el inyectado.

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

El script `scripts/backup_restore.py` guarda en un `.tar.gz` la base de datos y todos los artefactos (`ArtifactStore`), con un manifiesto que registra el SHA-256 de cada archivo:
- **PostgreSQL:** volcado de `pg_dump` en formato custom.
- **SQLite:** copia consistente con la API de `sqlite3`.

Cuándo falla:
- **`backup`:** si falta `pg_dump` o si falla, con un error claro que no muestra la contraseña, y sin dejar el archivo de salida. El `.tar.gz` se escribe primero como `.tmp` y se renombra al final: un fallo a medias no deja una copia rota ni pisa la anterior. Antes guardaba un comentario de texto en lugar del volcado y la copia parecía válida ([#159](https://github.com/sebdavid3/Cadenza/issues/159)).
- **`verify`:** si un hash no coincide, o si el archivo de PostgreSQL no es un volcado de `pg_dump`.
- **`restore`:** si falla `pg_restore`. La base se restaura primero y en una sola transacción que se detiene en el primer error (`--single-transaction --exit-on-error`), así que si falla queda como estaba. Los artefactos se copian solo después.

`pg_dump` y `pg_restore` deben ser de la misma versión que el servidor (PostgreSQL 16). Acepta la URL de SQLAlchemy (`postgresql+psycopg2://…`) y la traduce a la de libpq. La contraseña se pasa en `PGPASSWORD`, no en la línea de órdenes, donde se vería en la lista de procesos.

### 4.1 En local (SQLite o PostgreSQL con sus herramientas instaladas)

```bash
uv run --no-sync python scripts/backup_restore.py backup --output backup-2026-10-23.tar.gz
uv run --no-sync python scripts/backup_restore.py verify --archive backup-2026-10-23.tar.gz
uv run --no-sync python scripts/backup_restore.py restore --archive backup-2026-10-23.tar.gz --force
```

### 4.2 En el despliegue público (`docker-compose.prod.yml`)

El servicio `backup` (perfil `backup`, `Dockerfile.backup`) lleva el `pg_dump` 16 de la imagen de PostgreSQL. Monta el volumen de artefactos y el directorio de copias del host, `${CADENZA_BACKUP_DIR:-./backups}`, en `/backups`. Solo se ejecuta a petición. Las copias contienen todos los datos: el directorio debe tener permisos 700 y no salir del servidor sin cifrar. El contenedor corre como root, así que las copias pertenecen a root. Al restaurar, da los artefactos que copia, sus carpetas y la carpeta de artefactos al usuario de la API (`CADENZA_ARTIFACTS_OWNER`, `10001:10001`): así la API puede seguir escribiendo en las carpetas que crea la restauración, también si la restauración crea el volumen. Antes de tocar la base, rechaza la copia si algún destino sale de la carpeta de artefactos por un enlace simbólico (ADR-0029).

```bash
cd /opt/docker/cadenza
mkdir -p backups && chmod 700 backups
DC="docker compose -f docker-compose.prod.yml --env-file .env --profile backup"

# Crear y verificar una copia
$DC run --rm backup backup --output /backups/cadenza-$(date +%F-%H%M).tar.gz
$DC run --rm backup verify --archive /backups/cadenza-AAAA-MM-DD-HHMM.tar.gz

# Restaurar: con la API parada, para que nadie escriba mientras tanto
docker compose -f docker-compose.prod.yml stop api
$DC run --rm backup restore --archive /backups/cadenza-AAAA-MM-DD-HHMM.tar.gz
docker compose -f docker-compose.prod.yml start api
```

`restore` borra y recrea los objetos de la base de datos desde el volcado (`pg_restore --clean --if-exists --no-owner --single-transaction --exit-on-error`). Después copia los artefactos de la copia sobre los existentes, que son direccionados por contenido. Para comprobar una copia sin tocar la base de producción, se puede restaurar en una base aparte creada con `CREATE DATABASE`, pasando su URL en `CADENZA_DATABASE_URL`.

### 4.3 Copia diaria ([#174](https://github.com/sebdavid3/Cadenza/issues/174))

`deploy/copia-diaria.sh` hace una copia con el servicio `backup` y la verifica. Solo si la copia nueva es válida, borra las de más de `CADENZA_BACKUP_KEEP_DAYS` días (14 por defecto). Si algo falla, sale con un código distinto de 0 y deja una línea `ERROR` en el registro.

En el servidor del despliegue corre cada día a las 04:15 UTC (23:15 en Colombia) desde el cron de `papoi`. La línea está también en `~/scripts/crontab-papoi.txt`, el archivo desde el que se instala ese crontab:

```cron
15 4 * * * /bin/sh /opt/docker/cadenza/deploy/copia-diaria.sh >> /opt/docker/cadenza/backups/copias.log 2>&1
```

Para ver cómo van las copias:

```bash
tail -n 20 /opt/docker/cadenza/backups/copias.log
ls -la /opt/docker/cadenza/backups
```

Las copias se quedan en el mismo disco que los datos: protegen de errores y borrados, no de que falle el disco. Sacar una copia del servidor (cifrada) queda en manos del responsable.
