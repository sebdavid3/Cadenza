# ADR-0015: Operación y despliegue del backend

- **Estado:** Aceptado
- **Fecha:** 2026-10-08
- **Decisores:** Arquitecto de Software, Equipo de Desarrollo de Cadenza
- **Relacionado:** [ADR-0001](ADR-0001-monolito-modular-hexagonal.md), [ADR-0003](ADR-0003-separacion-planos-computo.md), [ADR-0004](ADR-0004-persistencia-postgresql-jsonb.md), [ADR-0005](ADR-0005-motor-omr-homr-baseline-oemer.md), [ADR-0008](ADR-0008-active-learning-model-registry.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md)

---

## Contexto

El desarrollo del backend de Cadenza se ejecutó inicialmente en entornos locales de desarrollo. No obstante, para garantizar la disponibilidad, seguridad, reproducibilidad e integración con el frontend en entornos de demostración y producción, se identificaron brechas operativas críticas (issue #40, deuda técnica D44):

1. **Monitoreo de salud:** Ausencia de sondas de liveness/readiness para balanceadores de carga y orquestadores (Docker Compose / Kubernetes).
2. **Trazabilidad y observabilidad:** Falta de correlación distribuida entre peticiones (`X-Request-ID`) y sesiones (`X-Session-ID`), y registro estructurado de accesos y latencias.
3. **Seguridad perimetral:** Necesidad de política restrictiva de CORS configurable por entorno y protección contra ataques de fuerza bruta en los endpoints de autenticación (`/auth/login`).
4. **Despliegue y secretos:** Requisito de TLS/HTTPS obligatorio fuera de desarrollo local y externalización rigurosa de secretos (`CADENZA_AUTH_SECRET_KEY`, credenciales de base de datos) fuera del control de versiones.
5. **Separación de planos de cómputo en contenedores:** `ARCHITECTURE.md` §4 estipula que el plano online (FastAPI + inferencia OMR liviana) se orquesta mediante Docker Compose, mientras que el plano offline (entrenamiento PyTorch y active learning intensivo) requiere un contenedor especializado con soporte para NVIDIA CUDA.
6. **Continuidad del negocio y recuperación ante desastres:** Necesidad de un procedimiento atómico para respaldar y restaurar conjuntamente la base de datos relacional y el almacenamiento de artefactos referenciados (`ArtifactStore`).

---

## Decisión

### 1. Entornos y arquitectura de despliegue

Se formaliza una arquitectura multicapa para demostración y producción:

- **Desarrollo local:** Ejecución directa mediante `uv run` o Docker Compose local con SQLite o PostgreSQL y motor `fake` u `homr` (CPU).
- **Entorno de demostración / producción:**
  - Despliegue mediante `docker-compose.yml` compuesto por:
    1. Servicio `postgres:16-alpine` con volumen persistente `postgres_data` y healthcheck `pg_isready`.
    2. Servicio `api` (FastAPI) empaquetado en imagen `Dockerfile` multistage, ejecutando migraciones automáticas Alembic antes de iniciar `uvicorn`.
    3. Servicio opcional `ml-batch` bajo el perfil `batch`, utilizando `Dockerfile.ml-cuda` con acceso a GPU NVIDIA (`deploy.resources.reservations.devices`).
  - **Terminación TLS / HTTPS:** Todo tráfico externo debe terminar en un reverse proxy seguro (Caddy o Nginx) con certificados TLS automáticos (Let's Encrypt). La API no expone puertos sin cifrar hacia redes públicas.
  - **Secretos:** Gestionados exclusivamente mediante variables de entorno inyectadas en tiempo de ejecución (`.env` protegido o gestor de secretos), validando que `CADENZA_AUTH_SECRET_KEY` contenga un mínimo de 32 bytes aleatorios.

### 2. Sondas de salud (`GET /health`)

Se implementa el endpoint `GET /health` bajo la categoría `System`, devolviendo `HealthStatusResponse`:
- **Base de datos:** Ejecución activa de `SELECT 1` sobre la sesión de base de datos (`connected` o `error`).
- **ArtifactStore:** Comprobación de accesibilidad y permisos de escritura/lectura en el directorio raíz del almacenamiento (`accessible` o `error`).
- **Motor OMR y Dispositivo:** Reporte del motor configurado (`omr_engine`) y del dispositivo de cómputo efectivo (`cpu`, `cuda`).
- **Código HTTP:** Devuelve `200 OK` si el estado es `healthy` (base de datos y artefactos operativos); en caso de fallo crítico en algún subsistema, responde `503 Service Unavailable` (`unhealthy`), permitiendo a orquestadores retirar el contenedor del enrutamiento.

### 3. Trazabilidad con `X-Request-ID` y registro estructurado

Se introduce un middleware HTTP que:
- Detecta o genera un identificador único `X-Request-ID` (UUID4) para cada petición y lo propaga en las cabeceras de respuesta.
- Extrae el identificador de sesión (`X-Session-ID` o desde la ruta `/sessions/{id}`).
- Registra una línea estructurada en los logs de acceso con: método, ruta, código HTTP, latencia en milisegundos (`duration_ms`), `request_id` y `session_id`.

### 4. CORS configurable y protección contra fuerza bruta

- **CORS:** Gobernado por la propiedad tipada `cors_origins` en `Settings` (`CADENZA_CORS_ORIGINS`). En desarrollo admite `*` y en producción se restringe a los dominios autorizados del cliente web. Expone cabeceras `X-Request-ID` y `X-API-Version`.
- **Límite de intentos de inicio de sesión (`LoginRateLimiter`):** Implementado en memoria por clave combinada `(IP:usuario)`. Bloquea peticiones tras superar el umbral configurable (`login_rate_limit_max_attempts=5` en `login_rate_limit_window_seconds=300`), respondiendo `HTTP 429 Too Many Requests` con la cabecera estándar `Retry-After`. Tras una autenticación exitosa, el historial de fallos se reinicia inmediatamente.

### 5. Imagen de contenedor con CUDA para el plano offline (`Dockerfile.ml-cuda`)

Se define la imagen `Dockerfile.ml-cuda` basada en `nvidia/cuda:12.8.0-runtime-ubuntu22.04` y Python 3.12, empaquetando las librerías con aceleración GPU (`torch`, `onnxruntime-gpu`, `musicdiff`) para ejecutar la suite offline `cadenza-ml` (`python -m ml`) de forma aislada sin sobrecargar el contenedor de la API online.

### 6. Copias de seguridad atómicas (`scripts/backup_restore.py`)

Se provee una herramienta de respaldo y recuperación:
- **Snapshot sincronizado:** Genera un archivo `.tar.gz` que incluye el volcado de la base de datos (copia en caliente SQLite mediante la API `backup` o `pg_dump` de PostgreSQL) junto con todos los archivos de `data/artifacts/`.
- **Manifiesto de integridad:** Incluye `manifest.json` con metadatos y hashes SHA-256 independientes para cada artefacto y el archivo de base de datos.
- **Verificación previa:** Todo proceso de restauración (`restore`) verifica primero los hashes SHA-256 (`verify`), impidiendo restaurar copias corruptas o manipuladas.

---

## Consecuencias

### Positivas
- Disponibilidad y resiliencia auditables mediante sondas de salud compatibles con Docker y orquestadores.
- Trazabilidad de incidentes facilitada por `X-Request-ID` y registro estructurado.
- Protección robusta contra ataques de denegación de servicio y fuerza bruta en credenciales.
- Aislamiento estricto de recursos de GPU entre la inferencia/API interactiva y los pipelines de entrenamiento por lotes.
- Garantía de integridad en procedimientos de backup y recuperación ante desastres (RPO / RTO predecible).

### Negativas / Mitigaciones
- `LoginRateLimiter` opera en memoria por réplica de API; en un clúster multi-instancia futuro requerirá un backend distribuido (Redis / Memcached). Para la arquitectura monolítica modular actual, el almacenamiento en memoria con locks de exclusión mutua es óptimo y autosuficiente.
