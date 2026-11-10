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
| `CADENZA_OMR_METER_FEATURES` | `str` | `numerator,symbol,implicit_tuplets` | Rasgos de la etapa del compás que corre tras HOMR ([ADR-0059](../adr/ADR-0059-compas-por-tramos-c-y-cortado-y-tresillos-implicitos-tras-homr.md)), separados por comas: `numerator` (el numerador de cada tramo, de lo que suman sus compases), `symbol` (4/4 como C y 2/2 como ¢) e `implicit_tuplets` (los tresillos sin marcar), o `all` / `none`. Un nombre desconocido impide arrancar. Lo que decidió queda en la procedencia de la sesión (`provenance.omr_stages`). |
| `CADENZA_ARTIFACTS_DIR` | `path` | `./data/artifacts` | Ruta raíz para el almacenamiento de archivos del `ArtifactStore`. |
| `CADENZA_AUTO_CREATE_SCHEMA` | `bool` | `false` | Si es `true`, crea DDL al arrancar (solo tests/dev). En producción usar Alembic. |
| `CADENZA_CORS_ORIGINS` | `list[str]` | `*` | Orígenes permitidos para peticiones cruzadas: `*` o `esquema://host[:puerto]` (sin ruta ni barra final), uno o varios separados por comas o en una lista JSON. `*` va solo y no envía credenciales; `[]` desactiva CORS (con Docker Compose, un valor vacío se convierte en `*`). Un valor mal escrito impide arrancar la API. |
| `CADENZA_LOGIN_RATE_LIMIT_MAX_ATTEMPTS` | `int` | `5` | Máximo de fallos antes de bloquear temporalmente intentos en `/auth/login`. |
| `CADENZA_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `int` | `300` | Ventana temporal en segundos (5 min) para la protección contra fuerza bruta. |
| `CADENZA_REGISTRATION_ENABLED` | `bool` | `false` | Abre `POST /auth/register` ([ADR-0022](../adr/ADR-0022-registro-de-cuentas-con-activacion.md), [ADR-0025](../adr/ADR-0025-registro-abierto-sin-aprobacion.md)): la cuenta nace activa y marcada como autorregistrada, y un investigador puede desactivarla. Apagado, la ruta responde 404 sea cual sea el cuerpo. Encendido exige `CADENZA_CORS_ORIGINS` sin `*` (si no, la API no arranca) y, para que el límite cuente por visitante, un proxy de confianza que dé la IP real ([#156](https://github.com/sebdavid3/Cadenza/issues/156)): sin él, todas las peticiones llegan con la IP del proxy y el límite es uno solo para todo el servicio. |
| `CADENZA_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS` | `int` | `5` | Intentos de registro por IP (red /64 en IPv6) en la ventana, como mínimo 1. Cuentan los que llegan a procesarse, también los que acaban en 409 (nombre ocupado); un cuerpo que no supera el esquema (422) no cuenta porque no toca la base de datos. |
| `CADENZA_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS` | `int` | `3600` | Ventana en segundos del límite de registros por IP, como mínimo 1. |
| `CADENZA_TRANSCRIBE_MAX_CONCURRENCY` | `int` | `2` | Transcripciones que la API admite a la vez, de 1 a 8, con un hilo cada una ([ADR-0024](../adr/ADR-0024-transcripciones-simultaneas.md)). HOMR no es seguro entre hilos y calcula de una en una; el resto espera su turno. Una petición sin hueco espera hasta 10 s y luego responde 503 con `Retry-After: 10`. Si el cliente se va a mitad, la transcripción termina, se guarda y entonces libera su hueco. |
| `CADENZA_TRANSCRIBE_JOBS_PER_USER` | `int` | `10` | Transcripciones en segundo plano que una persona puede tener en cola o en curso, de 1 a 100 ([ADR-0064](../adr/ADR-0064-transcripcion-en-segundo-plano-con-su-avance.md)); con el tope, 429, y la web sube las demás cuando termina alguna. |
| `CADENZA_TRANSCRIBE_JOBS_MAX` | `int` | `30` | Transcripciones en segundo plano (`POST /transcription-jobs`) en cola o en curso, de todas las personas, de 1 a 500 ([ADR-0064](../adr/ADR-0064-transcripcion-en-segundo-plano-con-su-avance.md)). Cada una guarda su imagen en memoria hasta transcribirse; con el tope, la API responde 503 con `Retry-After: 60`. La cola vive en la memoria del proceso: supone un solo proceso de la API, y un reinicio pierde lo que estaba en cola o en curso. |
| `CADENZA_SCORE_CACHE_MAX_ENTRIES` | `int` | `32` | Estados de sesión materializados (`ScoreIR`, MusicXML y mapa de tiempos) que la API guarda en memoria por `(sesión, seq, última edición)`, de 0 a 1024; 0 la desactiva ([ADR-0037](../adr/ADR-0037-una-edicion-en-un-solo-viaje.md)). Es de cada proceso: con una instancia de uvicorn, una caché. |
| `CADENZA_SUGGESTIONS_ENABLED` | `bool` | `false` | Activa la capa de sugerencias que aprende de las correcciones ([ADR-0036](../adr/ADR-0036-capa-de-sugerencias-aprendida.md)), global. Al arrancar, la API carga la versión promovida de `suggestion_model_versions` (migración `0013_suggestions`), comprueba el `sha256` de su artefacto en `CADENZA_ARTIFACTS_DIR` y su `feature_version`; si no hay versión o no cuadra, valida sin capa y lo registra (`suggestion_layer unavailable reason=…`). Una versión se promueve con `ml suggestions promote` (ver `ml/README.md`) y entra en vigor al reiniciar la API. Entre el congelado (#252) y el final del estudio no se promueve ninguna. |
| `CADENZA_SUGGESTIONS_MIN_LEVEL` | `str` | `high` | Con la capa activa, nivel de confianza mínimo de las sugerencias que se muestran, se guardan y se pueden aplicar: `high` o `medium` ([ADR-0036](../adr/ADR-0036-capa-de-sugerencias-aprendida.md), enmienda 19). El valor por defecto es la decisión del responsable para la condición asistida del estudio (#244). |
| `CADENZA_SUGGESTIONS_FAMILIES` | `str` | `accidental` | Con la capa activa, familias de las sugerencias que se muestran, separadas por comas: `accidental`, `duration`, `pitch`, `delete` e `insertion` (enmienda 19). Los hallazgos de las reglas se muestran siempre, aunque se queden sin sugerencias; los posibles errores propios (`learned.*`) de otra familia no. Al cargar la capa, la API registra la política (`suggestion_layer loaded … policy_min_level=… policy_families=…`); un nivel o una familia inválidos no impiden arrancar: la API valida sin capa y lo registra (`suggestion_layer unavailable reason=invalid_policy`). Como el resto, se lee al arrancar. |
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
- **Registro** abierto, sin aprobación (ADR-0025): `CADENZA_REGISTRATION_ENABLED` enciende la ruta de la API y, como argumento del build de `web`, los enlaces de la interfaz; cerrarlo y reabrirlo, en «Cerrar y reabrir el registro», más abajo. Solo admite `true` o `false`: la API aceptaría también `1`, `yes` u `on`, pero el build compara con `true` y dejaría ocultos los enlaces.
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
# En un comando, desde un equipo con el repositorio: ver «Desplegar dev en un comando», abajo.
$DC --profile backup run --rm backup backup --output /backups/cadenza-$(date +%F-%H%M).tar.gz
git pull --ff-only
$DC up -d --build
$DC --profile backup build backup   # la imagen de copias no se reconstruye sola con «up»
sh deploy/limpieza-docker.sh        # caché de construcción a 10 GB como mucho (#205)

# Parar y volver a arrancar: los volúmenes, y con ellos los datos, se conservan
$DC down
$DC up -d

# Retirar de internet sin parar los servicios, y volver a publicar
sudo tailscale funnel --https=443 off
sudo tailscale funnel --bg 8380
```

#### Desplegar `dev` en un comando ([#382](https://github.com/sebdavid3/Cadenza/issues/382))

`deploy/desplegar.sh` hace el «Actualizar» de arriba de una vez: copia previa con `verify --archive`, avance en *fast-forward* hasta el commit esperado de `origin/dev`, `up -d --build`, imagen de copias, limpieza y espera a `/api/health` (5 minutos como mucho). Desde un equipo con el repositorio, tras fusionar:

```bash
git fetch origin && ssh r2d2-cf "sh -s $(git rev-parse origin/dev)" < deploy/desplegar.sh
```

(`r2d2` en vez de `r2d2-cf` si Tailscale responde.) Se para sin tocar nada si `origin/dev` en el servidor no es el commit esperado (otra fusión entretanto: volver a lanzarlo), si el árbol del servidor tiene cambios sin comitear o si la copia no se verifica. Si la API no queda sana, lo dice, enseña sus últimas líneas y sale con 2, sin volver atrás: se vuelve a mano con la copia que nombra (§4.2). El 2026-11-09 desplegar así tardó unos 2,5 minutos. Los guiones de shell se sacan siempre con LF (`.gitattributes`): con CRLF, `sh` fallaría en el servidor.

- La primera actualización a una versión con #192 necesita además, una sola vez, la migración del volumen de artefactos (sección anterior). En el homelab se hizo la noche del 2026-10-23, hora de Colombia ([#203](https://github.com/sebdavid3/Cadenza/issues/203)): ninguna entrada quedó con otro dueño y la API arrancó `healthy` como `cadenza`.
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

#### Despliegue continuo desde `main` ([#337](https://github.com/sebdavid3/Cadenza/issues/337), [ADR-0062](../adr/ADR-0062-despliegue-continuo-desde-main-en-el-homelab.md))

`deploy/despliegue-continuo.sh` automatiza el procedimiento de «Actualizar» de arriba: cada 5 minutos trae `origin/main` y, si hay un commit nuevo cuyo flujo `CI` terminó en verde, hace la copia verificada, avanza en *fast-forward*, reconstruye, espera a que `/api/health` responda con la base de datos conectada (hasta 5 minutos) y limpia la caché de Docker. Si la API no queda sana, vuelve al commit anterior y descarta el nuevo. **Se activa después del estudio y de la promoción de `dev` a `main` ([#261](https://github.com/sebdavid3/Cadenza/issues/261)), no antes:** con `main` atrasado, avanzar a `main` sería volver atrás.

```bash
# Probar sin cambiar nada: dice qué commit desplegaría o por qué no
sh deploy/despliegue-continuo.sh --simular

# Activar (crontab del usuario del despliegue; gh vive en ~/.local/bin y debe estar autenticado)
*/5 * * * * PATH=$HOME/.local/bin:/usr/bin:/bin /bin/sh /opt/docker/cadenza/deploy/despliegue-continuo.sh >> /opt/docker/cadenza/backups/despliegue.log 2>&1

# Pausar y reanudar sin tocar el cron
touch ~/.local/state/cadenza-despliegue/pausado
rm ~/.local/state/cadenza-despliegue/pausado
```

- Sin novedad, con la CI en curso o en pausa no escribe en el log. Un error que se repetiría (árbol con cambios, `main` reescrita, CI inaccesible) se registra una vez.
- Con la CI roja no se despliega, pero si se relanza y pasa, sí. Un commit que no arrancó queda en `~/.local/state/cadenza-despliegue/rechazados` y no se reintenta: lo arregla un commit posterior, o se quita de ese archivo para reintentarlo.
- Si la copia previa falla, si el checkout falla o si tampoco arranca la versión anterior (la nueva ya migró la base: el log dice «ERROR GRAVE» con el nombre de la copia, que se restaura a mano, §4.2), el script se pone en pausa con el motivo en el archivo `pausado` y avisa. Se reanuda borrando ese archivo.
- La promoción de `dev` a `main` se hace con un merge, no con *squash*: así el primer paso de producción a `main` es un *fast-forward*. Si no, ese paso se da a mano (copia, `git checkout -B main origin/main`, `$DC up -d --build`).
- Variables, con su valor por defecto: `CADENZA_DESPLIEGUE_RAMA` (`main`), `CADENZA_DESPLIEGUE_REPO` (`sebdavid3/Cadenza`), `CADENZA_DESPLIEGUE_FLUJO` (`CI`), `CADENZA_DESPLIEGUE_AVISO` (vacío; un comando que recibe el mensaje como argumento, por ejemplo un `curl` a un servicio de avisos), `CADENZA_DESPLIEGUE_ESTADO` (`~/.local/state/cadenza-despliegue`), `CADENZA_DESPLIEGUE_SALUD` (`http://127.0.0.1:<CADENZA_WEB_PORT del .env>/api/health`), `CADENZA_DESPLIEGUE_ESPERA` (300 s) y `CADENZA_DESPLIEGUE_INTERVALO` (10 s).

#### Cerrar y reabrir el registro ([#248](https://github.com/sebdavid3/Cadenza/issues/248))

Durante el estudio ([#253](https://github.com/sebdavid3/Cadenza/issues/253)) el registro está cerrado: solo entran las cuentas que crea un investigador (D59 en su mínimo; los límites completos del registro abierto quedan para [#194](https://github.com/sebdavid3/Cadenza/issues/194)). Se cierra antes del congelado ([#252](https://github.com/sebdavid3/Cadenza/issues/252)) y se reabre, si se quiere, al acabar el estudio.

Una sola línea del `.env` del servidor, `CADENZA_REGISTRATION_ENABLED`, gobierna las dos mitades. La API la lee al arrancar: cerrado, `POST /auth/register` responde 404 sea cual sea el cuerpo. La web la recibe como argumento del build (`VITE_REGISTRATION_ENABLED`): cerrado, ni la landing ni `/entrar` enlazan al registro, `/registro` dice «Registro cerrado» y lleva a entrar, sin formulario, y `/cuentas` lo indica. El contrato de la API no cambia. Como la web la fija al construirse, **cambiarla exige reconstruir `web`**: un `up -d` sin `build` deja la interfaz anterior, que enlazaría un registro que la API ya rechaza (la vista lo traduce por «El registro de cuentas no está abierto en este servidor»). Solo admite `true` o `false`, como se explica arriba. Si el `.env` no tiene la línea, el `sed` no hace nada: al cerrar da igual, porque el compose toma `false` por defecto, pero al reabrir hay que añadirla. `up -d api web` reinicia la API: corta las transcripciones en curso y `/api` responde 502 hasta que carga HOMR (hasta 2 minutos), así que se hace sin nadie trabajando, antes del piloto ([#251](https://github.com/sebdavid3/Cadenza/issues/251)) o del congelado.

```bash
DC="docker compose -f docker-compose.prod.yml --env-file .env"

# Cerrar: la variable a false, la imagen de la web reconstruida y las dos recreadas
sed -i 's/^CADENZA_REGISTRATION_ENABLED=.*/CADENZA_REGISTRATION_ENABLED=false/' .env
grep '^CADENZA_REGISTRATION_ENABLED=' .env    # una sola línea, con false; si no sale nada, añadirla
$DC build web
$DC up -d api web                             # recrea la API (cambió su entorno) y la web (su imagen)

# Comprobar, en el puerto de CADENZA_WEB_PORT (8380 por defecto): cerrado da 404; abierto, 422
# (un cuerpo vacío no crea nada ni cuenta en el límite de la API)
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8380/api/auth/register \
  -H 'Content-Type: application/json' -d '{}'

# Reabrir: lo mismo con true
sed -i 's/^CADENZA_REGISTRATION_ENABLED=.*/CADENZA_REGISTRATION_ENABLED=true/' .env
$DC build web
$DC up -d api web
```

#### Encender el registro con el permiso de uso de los datos ([#378](https://github.com/sebdavid3/Cadenza/issues/378))

El registro pide ahora, con una casilla obligatoria, el permiso de uso de los datos ([ADR-0065](../adr/ADR-0065-permiso-de-uso-de-los-datos-al-registrarse.md)): la cuenta guarda cuándo se dio y qué versión del texto (`/uso-de-los-datos`). El responsable aprobó el texto el 2026-11-09; **encenderlo en producción sigue siendo decisión suya**. Encenderlo son dos variables y reconstruir la web:

1. **`CADENZA_REGISTRATION_ENABLED=true`** (API): abre `POST /auth/register`. La API la lee al arrancar y aplica la migración `0017_users_data_consent` si falta.
2. **`VITE_REGISTRATION_ENABLED=true`** (web): enseña los enlaces al registro y el formulario con el aviso y la casilla. Se fija al construir la imagen: en `docker-compose.prod.yml` la recibe del mismo `CADENZA_REGISTRATION_ENABLED` del `.env` como argumento del build, así que en el servidor basta la línea del `.env`, pero **hay que reconstruir `web`**; en otro despliegue, se pasa como argumento del build (`Dockerfile.web`).

Con el bloque de arriba («Reabrir»: la línea del `.env` a `true`, `$DC build web` y `$DC up -d api web`). Comprobar después: el `curl` de arriba da 422 (abierto), `/registro` enseña «Uso de tus datos» con la casilla y el enlace al texto completo, `/uso-de-los-datos` responde 200, y una cuenta creada así tiene `data_consent: true` en `GET /api/auth/me`. Desde «Tu cuenta» se retira y se vuelve a dar.

Después de cerrarlo:
- **En el navegador**, en escritorio y en móvil: la landing y `/entrar` sin «Créala» ni «Crear una cuenta», y `/registro` con «Registro cerrado». `index.html` no se guarda en caché, pero una pestaña que ya estaba abierta conserva la interfaz anterior hasta recargarla.
- **Las cuentas que ya se crearon desde el registro siguen activas**: cerrar no las borra ni las desactiva, así que pueden entrar y ocupar los huecos de transcripción ([ADR-0024](../adr/ADR-0024-transcripciones-simultaneas.md)). Un investigador las revisa en `/cuentas` (origen «Registro») y desactiva las que no deban entrar durante el estudio. Desactivar es reversible y no borra sus sesiones; un token ya emitido deja de valer en la petición siguiente. Sus sesiones ya quedan fuera del dataset del plano offline (`build-dataset` excluye las cuentas autorregistradas). Las de los participantes las crea el investigador ([#249](https://github.com/sebdavid3/Cadenza/issues/249)).
- **En el congelado** ([#252](https://github.com/sebdavid3/Cadenza/issues/252)) se anota que `CADENZA_REGISTRATION_ENABLED=false`, el código del `curl` (404) y las cuentas del registro que se desactivaron. Al reabrirlo, se reactivan las que se quiera desde `/cuentas`.

Comprobado en local el 2026-10-31 con la API en `127.0.0.1` y SQLite en disco, y la web de desarrollo de Vite con la variable del build a `true` y a `false` ([#248](https://github.com/sebdavid3/Cadenza/issues/248)): con los dos abiertos, la landing enlaza el registro y una cuenta se crea y entra; con la API cerrada y la web todavía abierta, `POST /auth/register` da 404 con cualquier cuerpo y el formulario dice «El registro de cuentas no está abierto en este servidor»; con los dos cerrados, ni la landing ni `/entrar` enlazan el registro y `/registro` dice «Registro cerrado», sin formulario, a 1440 y 390 px y sin desplazamiento horizontal. La cuenta creada desde el registro siguió entrando hasta que un investigador la desactivó en `/cuentas`; después, su acceso dio 401.

#### Transcribir sin cuenta desde la portada ([#278](https://github.com/sebdavid3/Cadenza/issues/278), [ADR-0054](../adr/ADR-0054-transcribir-sin-cuenta-desde-la-portada.md))

Comparte el interruptor del estudio con el registro: **apagado por defecto y durante el estudio** ([#253](https://github.com/sebdavid3/Cadenza/issues/253)), porque gasta los huecos de HOMR que usan los participantes. Se enciende, si se quiere, al acabar el estudio, igual que se reabre el registro: una línea del `.env`, `CADENZA_ANONYMOUS_PREVIEW_ENABLED`, que la API lee al arrancar (apagada, `POST /previews` y `POST /previews/{id}/claim` responden 404) y la web recibe en el build (`VITE_ANONYMOUS_PREVIEW_ENABLED`). **Cambiarla exige reconstruir `web`**; con la web encendida y la API apagada, el recuadro de la portada vuelve a pedir que se entre. Encendida exige CORS cerrado al origen público, como el registro.

```bash
DC="docker compose -f docker-compose.prod.yml --env-file .env"

# Encender (al acabar el estudio, y solo con los dos fallos de #278 resueltos): la variable a true,
# la web reconstruida y las dos recreadas
sed -i 's/^CADENZA_ANONYMOUS_PREVIEW_ENABLED=.*/CADENZA_ANONYMOUS_PREVIEW_ENABLED=true/' .env
grep '^CADENZA_ANONYMOUS_PREVIEW_ENABLED=' .env    # una sola línea; si no sale nada, añadirla
$DC build web
$DC up -d api web

# Comprobar: apagada da 404; encendida, 422 (sin archivo no transcribe ni cuenta en el límite)
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8380/api/previews

# Apagar: lo mismo con false
```

- **Límites:** la API admite como mucho una transcripción sin cuenta a la vez y nunca espera un hueco de HOMR (sin hueco libre, 503); cuenta `CADENZA_ANONYMOUS_PREVIEW_RATE_LIMIT_MAX_ATTEMPTS` (5) por IP en `…_WINDOW_SECONDS` (3600), y guarda como mucho `CADENZA_ANONYMOUS_PREVIEW_MAX_ACTIVE` (20) a la vez. Nginx añade una por minuto por visitante (no admite tasas por hora), con ráfagas de tres, y una conexión abierta (`location = /api/previews`).
- **Caducidad:** cada transcripción sin cuenta caduca a la hora (`CADENZA_ANONYMOUS_PREVIEW_TTL_SECONDS`) y se borra, con su imagen, al llegar la siguiente o al reclamar una; al arrancar, la API borra solo las caducadas, así que las vigentes al apagar el interruptor se quedan hasta un reinicio posterior a su caducidad (anotado en #278). Vive en la tabla `previews` (migración 0016), con la imagen en la fila: entra en las copias de seguridad de la base de esa hora.
- **Al reclamarla** pasa a ser una sesión de la cuenta que entra, como cualquier otra: si es una cuenta del registro, queda fuera del dataset como las demás autorregistradas.

#### Activar la capa de sugerencias (congelado, [#252](https://github.com/sebdavid3/Cadenza/issues/252), [#333](https://github.com/sebdavid3/Cadenza/issues/333))

En la condición asistida del estudio ([#244](https://github.com/sebdavid3/Cadenza/issues/244); [ADR-0036](../adr/ADR-0036-capa-de-sugerencias-aprendida.md), enmienda 19), la capa de sugerencias muestra solo las sugerencias de alteración de confianza alta (`CADENZA_SUGGESTIONS_MIN_LEVEL=high`, `CADENZA_SUGGESTIONS_FAMILIES=accidental`, que son los valores por defecto del compose y de la API). En la condición `unassisted` no corren ni las reglas ni la capa (D38). Entre el congelado ([#252](https://github.com/sebdavid3/Cadenza/issues/252)) y el final del estudio no se promueve ninguna versión (ADR-0036 §8, enmienda 14).

El corpus de entrenamiento (`results/correction_corpus.jsonl`, de `exp_12`, [#255](https://github.com/sebdavid3/Cadenza/issues/255)) vive en el portátil y solo se lee. En el servidor, PostgreSQL no publica su puerto, el volumen `cadenza-prod_artifacts_data` pertenece al usuario `cadenza` (UID y GID 10001, [ADR-0029](../adr/ADR-0029-api-con-usuario-sin-privilegios.md)) y la imagen `cadenza-api:prod` incluye los paquetes del workspace en `/app/packages/` (con `cadenza.learning` ya compilado a bytecode, sin dependencias externas), pero no instala el `.pth` editable de `cadenza-learning` ni copia `ml/` ni `configs/`. Por eso la promoción se ejecuta con un contenedor efímero del propio servicio `api` (`run --rm --no-deps`), que ya corre en la red del compose con el UID 10001, recibe `CADENZA_DATABASE_URL` del `.env` sin exponerla en la lista de procesos del host y monta el volumen de artefactos en `/app/data/artifacts`: basta con montar en solo lectura `ml/` y `configs/` del clon de `/opt/docker/cadenza`, montar la carpeta con el modelo y el informe fuera del repositorio y añadir `/app:/app/packages/learning/src` a `PYTHONPATH`.

1. **En el portátil (PowerShell): entrenar, evaluar y enviar al servidor.** El entrenamiento es determinista (`seed: 42` en `configs/learning/suggestions.json`): con el corpus `a57817f105efd68968f459cc9cf7850a5438ed85e744f8476ca6fd12f44f0687` y la configuración `deae5234c038916d240008ed228e4e9738bb9df99eb86474b85a237a5593090e`, el artefacto tiene siempre `sha256` `dac502e33667a15fb42cba30f147735f14328e4f3a6089221b372c5c89c46bd4`. Las salidas se escriben fuera de `results/` y de `data/` y se copian a `/opt/docker/cadenza-capa` en el servidor (fuera de `/opt/docker/cadenza`, para que el árbol de `git` siga limpio):

```powershell
$capa = Join-Path $env:TEMP "cadenza-capa"
New-Item -ItemType Directory -Force -Path $capa | Out-Null

uv run --no-sync python -m ml suggestions train `
  --corpus results/correction_corpus.jsonl `
  --config configs/learning/suggestions.json `
  --output "$capa\modelo.json"

uv run --no-sync python -m ml suggestions evaluate `
  --model "$capa\modelo.json" `
  --corpus results/correction_corpus.jsonl `
  --output "$capa\informe.json"

Get-FileHash "$capa\modelo.json","$capa\informe.json" -Algorithm SHA256
# modelo.json ha de dar DAC502E33667A15FB42CBA30F147735F14328E4F3A6089221B372C5C89C46BD4

ssh papoi@r2d2 "mkdir -p /opt/docker/cadenza-capa"
scp "$capa\modelo.json" "$capa\informe.json" papoi@r2d2:/opt/docker/cadenza-capa/
```

2. **En el servidor (`/opt/docker/cadenza`): copia previa, promoción y encendido.** Si el `.env` se creó antes de [#333](https://github.com/sebdavid3/Cadenza/issues/333) y aún no tiene la línea `CADENZA_SUGGESTIONS_ENABLED=...`, el `sed` no cambiaría nada: el comando comprueba si existe y, si no, la añade. Recrear `api` (`$DC up -d api`) corta las transcripciones en curso y `/api` responde 502 hasta que carga HOMR (hasta 2 minutos), así que se hace sin nadie trabajando:

```bash
cd /opt/docker/cadenza
DC="docker compose -f docker-compose.prod.yml --env-file .env"

# 1. Comprobar el sha256 recibido y hacer copia de seguridad verificada antes de tocar la base
sha256sum /opt/docker/cadenza-capa/modelo.json /opt/docker/cadenza-capa/informe.json
# modelo.json: dac502e33667a15fb42cba30f147735f14328e4f3a6089221b372c5c89c46bd4
BACKUP="/backups/cadenza-$(date +%F-%H%M).tar.gz"
$DC --profile backup run --rm backup backup --output "$BACKUP"
$DC --profile backup run --rm backup verify --archive "$BACKUP"

# 2. Promover la versión con el usuario cadenza (UID 10001) en la red y el volumen de la API
$DC run --rm --no-deps   -v "$PWD/ml:/app/ml:ro"   -v "$PWD/configs:/app/configs:ro"   -v "/opt/docker/cadenza-capa:/capa:ro"   -e PYTHONPATH=/app:/app/packages/learning/src   api python -m ml suggestions promote   --model /capa/modelo.json   --report /capa/informe.json   --artifacts-dir /app/data/artifacts   --version sug-estudio-20261108

# 3. Encender el interruptor en .env (la política por defecto ya es high y accidental) y recrear api
if grep -q '^CADENZA_SUGGESTIONS_ENABLED=' .env; then
  sed -i 's/^CADENZA_SUGGESTIONS_ENABLED=.*/CADENZA_SUGGESTIONS_ENABLED=true/' .env
else
  printf '
CADENZA_SUGGESTIONS_ENABLED=true
' >> .env
fi
grep '^CADENZA_SUGGESTIONS_' .env     # ha de salir CADENZA_SUGGESTIONS_ENABLED=true
$DC up -d api
```

3. **Comprobar en el registro de la API.** Al terminar de arrancar `api` (`$DC ps`), el registro ha de mostrar la línea `suggestion_layer loaded` con la versión promovida y la política del estudio:

```bash
$DC logs --no-color --tail=50 api | grep suggestion_layer
# INFO:     suggestion_layer loaded version=sug-estudio-20261108 feature_version=1 families=accidental policy_min_level=high policy_families=accidental
```

Si la capa no pudiera cargarse (por ejemplo, `CADENZA_SUGGESTIONS_ENABLED=true` sin versión promovida, un `sha256` que no coincide en `/app/data/artifacts`, otra `feature_version` o una política inválida), la API arranca igualmente sana (`GET /api/health` responde 200), valida solo con las reglas y deja en el registro `WARNING:  suggestion_layer unavailable reason=…` (`no_promoted_version`, `invalid_artifact`, `feature_version` o `invalid_policy`).

4. **Cómo apagarla si hiciera falta** (sin borrar la versión promovida ni tocar la base de datos):

```bash
sed -i 's/^CADENZA_SUGGESTIONS_ENABLED=.*/CADENZA_SUGGESTIONS_ENABLED=false/' .env
grep '^CADENZA_SUGGESTIONS_ENABLED=' .env    # una sola línea, con false
$DC up -d api
```

5. **Qué se anota en el congelado** ([#252](https://github.com/sebdavid3/Cadenza/issues/252)):
   - el nombre de la versión promovida (`sug-estudio-20261108`);
   - el `sha256` del artefacto (`dac502e33667a15fb42cba30f147735f14328e4f3a6089221b372c5c89c46bd4`), el del corpus (`a57817f105efd68968f459cc9cf7850a5438ed85e744f8476ca6fd12f44f0687`) y el del informe de evaluación;
   - la línea `suggestion_layer loaded … policy_min_level=high policy_families=accidental` del registro de `api`;
   - y que en una sesión de prueba en condición `assisted` la procedencia trae `"suggestions_version": "sug-estudio-20261108"`.

Ensayado de punta a punta en el portátil el 2026-11-03 ([#333](https://github.com/sebdavid3/Cadenza/issues/333)) con `docker compose -f docker-compose.prod.yml -p cadenza-ensayo` en `127.0.0.1:18380` (retirado después con `down -v`):
- Dos entrenamientos seguidos sobre `results/correction_corpus.jsonl` dan el mismo `sha256` (`dac502e33667a15fb42cba30f147735f14328e4f3a6089221b372c5c89c46bd4`), idéntico al de `results/rules_catalog_v2/exp_14_politica_alteraciones_alta/suggestion_layer_artifact.json`; el informe (`933e97ac815b1893b5efc8fe52366b807ba2bfa2d28a2c2196fceedc6b3172af`, 352 incipits) coincide en todas sus métricas con `promotion_metrics` de `exp_14_politica_alteraciones_alta/suggestion_layer_summary.json` (`learned.f1 = 0,0856` frente a `0,0`, `rule_findings.top1_accuracy = 0,8608` —68 de 79— frente a `0,6709` —53 de 79—; en `test.rule_suggestions` de ese resumen salen 40 de 79 porque `exp_14` filtra además la prueba por la política `min_level=high, families=accidental`, dejando las 45 sugerencias de alteración de confianza alta con 40 aciertos, mientras que `evaluate` mide el modelo sin la política de visualización, ADR-0036 enmienda 19).
- Con `CADENZA_SUGGESTIONS_ENABLED=true` antes de promover, la API arranca en `healthy` y registra `WARNING:  suggestion_layer unavailable reason=no_promoted_version`. Un intento de `promote` con un modelo cuyo `sha256` no coincide con `model_sha256` del informe termina con código 1 (`Error: el informe no es de este artefacto (model_sha256 distinto)`).
- Al promover con `$DC run --rm --no-deps` (`sug-20261103`), el artefacto queda en `/app/data/artifacts/sha256/da/c5/dac502e3…` con dueño `cadenza:cadenza` (`10001:10001`). Al recrear `api`, registra `INFO:     suggestion_layer loaded version=sug-20261103 feature_version=1 families=accidental policy_min_level=high policy_families=accidental`.
- Transcrito el incipit `000100471-1_1_1` por `http://127.0.0.1:18380/api/transcribe`: en `assisted`, `GET /api/sessions/{id}` devuelve `provenance.suggestions_version = "sug-20261103"` y el hallazgo `accidental.repeated` del c. 3 con su sugerencia (`SetAccidental`, `b` → `""`, `confidence: 0.85`, `confidence_level: "high"`, `source: "learned"`); en `unassisted`, `provenance.suggestions_version = null` y `findings: []`.
- Alterado el archivo del artefacto en el volumen y reiniciada `api`, el servicio arranca en `healthy` (200 en `/api/health`) y registra `WARNING:  suggestion_layer unavailable reason=invalid_artifact version=sug-20261103 error=el sha256 del artefacto (…) no es el registrado (dac502e3…)`.

#### Espacio en disco de Docker ([#205](https://github.com/sebdavid3/Cadenza/issues/205))

**Qué pasaba.** Antes de #205, cada construcción de la API con código nuevo dejaba unos 2,5 GB en la caché de construcción. El `Dockerfile` copiaba el código antes de instalar las dependencias, así que cada cambio de código:
- repetía `uv sync` (una capa de 1,312 GB) y la descarga de los pesos de HOMR;
- y la etapa final copiaba otra vez todo `/app`, entorno virtual incluido (1,218 GB).

El 2026-10-23 la caché llegó a 42,43 GB (231 entradas, todas de Cadenza), con el disco al 83 %. Se liberó con `docker builder prune -af` y `docker image prune -f`: la caché quedó en 0 B y el disco al 75 % (115 GB libres), con los servicios en marcha.

**Ahora.** La etapa `deps` instala las dependencias y los pesos de HOMR antes de copiar el código, solo con el lockfile y los `pyproject.toml`. La etapa final copia el entorno virtual de `deps` aparte de los paquetes del workspace y del código, que son lo único que cambia de una versión a otra. La construcción falla si a la imagen final le falta algún archivo de esos paquetes, y una prueba (`apps/api/tests/test_dockerfile.py`) fija todo esto. Medido en el servidor con un clon desechable:
- Tras un cambio solo de código, la caché crece 20 MB y 19 MB en dos reconstrucciones seguidas, que tardan 13 s y 9 s. Antes, 2,5 GB por reconstrucción.
- Con las dependencias antes del código, pero el entorno virtual copiado entero a la etapa final, crecía todavía 1,23 GB: el `RECORD` y el `uv_cache.json` de los paquetes del workspace cambian con cada construcción.
- El entorno virtual de la imagen final es idéntico al del builder: 16.174 archivos, ninguna diferencia.

**Tope.** `deploy/limpieza-docker.sh` deja la caché de construcción en `CADENZA_BUILD_CACHE_MAX` como mucho (10 GB por defecto), quedándose con lo usado más recientemente, y borra las imágenes colgantes.
- No toca volúmenes, contenedores ni imágenes con nombre, tampoco las de otros proyectos del servidor. La caché de construcción y las imágenes colgantes sí son de todo el servidor.
- El tope es un objetivo: la caché que respalda imágenes existentes no se libera. Con 3 GB, la prueba dejó 4,9 GB, y la reconstrucción siguiente tardó 9 s.
- Corre después de cada actualización (el procedimiento de arriba) y cada domingo desde el cron de `papoi`, después de la copia diaria. El servidor está en `Etc/UTC`. La línea está también en `~/scripts/crontab-papoi.txt`, desde el que se instala ese crontab. Se instaló el 2026-10-24 ([#207](https://github.com/sebdavid3/Cadenza/issues/207)); la versión anterior del archivo quedó en `crontab-papoi.txt.antes-205`:

```cron
45 4 * * 0 /bin/sh /opt/docker/cadenza/deploy/limpieza-docker.sh >> /opt/docker/cadenza/backups/limpieza-docker.log 2>&1
```

Comprobado al instalarla: la orden de la línea, con el entorno mínimo de cron (`env -i` con `PATH=/usr/bin:/bin`), termina con 0 y deja en `limpieza-docker.log` las líneas «antes» y «después». La primera ejecución programada es el domingo 2026-10-25 a las 04:45 UTC. Para ver cómo va:

```bash
tail -n 4 /opt/docker/cadenza/backups/limpieza-docker.log
```

Quedan fuera, a decisión del responsable:
- **La recolección de basura de BuildKit en `/etc/docker/daemon.json`.** Necesita `sudo` y reiniciar Docker, y con él todos los servicios del servidor.
- **Unos 4,8 GB de imágenes de otros proyectos** sin contenedor (`amazon/aws-cli`, `amazon/dynamodb-local`, `mcr.microsoft.com/playwright`).

### 2.3 Ejecución del plano offline con GPU (perfil batch)

Para correr jobs de aprendizaje (la capa de sugerencias, `ml suggestions`) o experimentos con aceleración NVIDIA CUDA:

```bash
docker compose --profile batch run --rm ml-batch --help
docker compose --profile batch run --rm ml-batch suggestions --help
```

> [!WARNING]
> Hoy la imagen `Dockerfile.ml-cuda` no se construye (deuda D53): pide `--extra torch --extra metrics` a la raíz del workspace, que no define extras (también en su alternativa `|| uv sync ...`), fija uv 0.5.21, anterior al formato del lockfile, y copia el `pyproject.toml` de `apps/api`, miembro del workspace, pero no su código. Su arreglo va con el ajuste fino real del modelo ([#103](https://github.com/sebdavid3/Cadenza/issues/103)), que queda fuera de la entrega de noviembre de 2026 (trabajo futuro).

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

Asimismo, el middleware de observabilidad asigna a cada petición la cabecera `X-Request-ID` y emite un registro estructurado al completar cada solicitud. El identificador es el del cliente si tiene la forma `[A-Za-z0-9._-]{1,64}` (la web envía uno por petición, `web-…`); si no, uno nuevo. En el despliegue público, Nginx deja pasar el del cliente con esa misma forma y, si no, pone su `$request_id` (§2.2, [#275](https://github.com/sebdavid3/Cadenza/issues/275)). Cada respuesta lleva además `Server-Timing` con el tiempo de cada etapa en milisegundos (`db`, `materialize`, `export`, `timing`, `serialize` y `total`; [ADR-0037](../adr/ADR-0037-una-edicion-en-un-solo-viaje.md)), que el navegador muestra en sus herramientas de red:

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
