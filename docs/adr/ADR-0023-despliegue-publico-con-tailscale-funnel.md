# ADR-0023: Despliegue público en el homelab con Tailscale Funnel

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Dirección del proyecto Cadenza (decisión aprobada por el responsable el 2026-10-23), Equipo de Desarrollo
- **Relacionado:** [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md) (concreta su §1), [ADR-0016](ADR-0016-transcripcion-sincrona-vs-asincrona.md), [ADR-0019](ADR-0019-base-del-cliente-web.md), [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md)

---

## Contexto

Cadenza se publica en el servidor doméstico del responsable (`r2d2`), accesible por Tailscale. ADR-0015 exige TLS fuera de local con un proxy inverso, secretos solo por entorno y ningún puerto sin cifrar expuesto, pero no decide cómo llega el tráfico público ni cómo se sirve el frontend.

Reconocimiento en solo lectura del 2026-10-23: Ubuntu 26.04.1, Intel i5-10300H (4 núcleos, 8 hilos), 7,1 GiB de RAM, 126 GB libres, Docker 29.9.2 con Compose v5.6.1, RTX 2060 de 6 GB con el runtime `nvidia` (la usa Immich), Tailscale 1.104.2 con Funnel permitido en el tailnet (puertos 443, 8443 y 10000) y sin configuración de `serve`. Ya corren Immich y otros servicios; no hay proxy inverso.

Opciones de exposición: Tailscale Funnel (HTTPS en `*.ts.net`, sin dominio ni router), Cloudflare Tunnel (exige un dominio en Cloudflare) o Caddy con redirección de puertos (exige dominio, acceso al router y exponer la IP doméstica).

## Decisión

1. **Exposición con Tailscale Funnel** en el puerto 443: `https://r2d2.tailcacb19.ts.net`. Tailscale termina TLS con un certificado de Let's Encrypt para ese nombre y reenvía al servicio web local. No se abre ningún puerto en el router ni se compra un dominio.
2. **Servicio web propio** (`web`, Nginx sin privilegios) que sirve el `dist/` de `apps/web` con respaldo a `index.html` para las rutas de la SPA y reenvía `/api/*` a `api:8000` quitando el prefijo, igual que el proxy de desarrollo de Vite (ADR-0019). Resuelve `api` con el DNS de Docker en cada petición, para no quedarse con una dirección antigua si la API se recrea. Solo publica `127.0.0.1:${CADENZA_WEB_PORT}` (8380 por defecto) en el host; Funnel apunta a ese puerto.
3. **PostgreSQL y la API sin puertos publicados**: solo los alcanza la red interna de Compose.
4. **IP real del cliente.** Funnel, en modo proxy HTTP (`tailscale funnel --bg 8380`), reenvía la petición a `127.0.0.1:8380` con `X-Forwarded-For`, y el contenedor `web` la ve llegar desde la pasarela de su red. La red de Compose tiene una subred fija (`10.77.0.0/24`, pasarela `10.77.0.1`, `web` en `10.77.0.10`) para que la confianza sea exacta: Nginx cree la cabecera solo si la petición llega de la pasarela, toma su última dirección (la que añadió Funnel, no la que pudiera inventar el cliente) y la reenvía a la API **sustituyendo** `X-Forwarded-For` y vaciando `Forwarded`. Uvicorn arranca con `--proxy-headers` y `--forwarded-allow-ips` (`CADENZA_FORWARDED_ALLOW_IPS`) limitado a la IP de `web`: otro contenedor de la red no puede hacerse pasar por un visitante. Así, los límites del login (ADR-0015) y del registro (ADR-0022) cuentan por visitante y no por proxy. Los modos TCP de Funnel (`--tcp`, `--tls-terminated-tcp`) quedan excluidos: no añaden la cabecera, todos los visitantes compartirían la IP de la pasarela y cualquiera podría inventarse la suya.
5. **CORS** limitado al origen público (`CADENZA_CORS_ORIGINS=https://r2d2.tailcacb19.ts.net`); el frontend llama a la API en el mismo origen bajo `/api`.
6. **API en CPU.** Se usa la imagen actual (HOMR con `onnxruntime` de CPU, ADR-0018). Medido en el servidor el 2026-10-23: un incipit de PrIMuS tarda 2,71 s en la primera petición y 2,23 s en la siguiente, y la API ocupa unos 600 MiB en reposo. Si las páginas compuestas se acercan al timeout de 30 s del cliente (ADR-0016), una variante con GPU será un issue aparte.
7. **Registro.** `CADENZA_REGISTRATION_ENABLED` enciende la ruta de la API (ADR-0022) y, como argumento del build de `web` (`VITE_REGISTRATION_ENABLED`), los enlaces de la interfaz; las dos cosas se encienden juntas.
8. **Defensa en Nginx.** Además de los límites de la API, Nginx limita por visitante (la IPv4, o la red /64 de una IPv6) el acceso y el registro (10 por minuto cada uno, con ráfagas de 10 y cuerpos de hasta 16 KB) y las transcripciones abiertas a la vez (4), rechaza con 400 las rutas con caracteres de control (`/api/auth/login%0A` esquivaría la `location` exacta y la API la atendería igual), envía una política de seguridad de contenido (`script-src 'self'`; `style-src` admite `'unsafe-inline'` porque OSMD dibuja con atributos `style`), comprime con gzip y no publica la documentación interactiva de la API (`/api/docs`, `/api/redoc`, `/api/openapi.json`). Los contenedores rotan sus registros, `api` y `web` arrancan sin capacidades de Linux y sin poder ganar privilegios, y la API tiene un tope de memoria de 3 GiB.
9. **Secretos y datos.** `CADENZA_AUTH_SECRET_KEY` y la contraseña de PostgreSQL se generan en el servidor (`openssl rand -hex 32`) en `/opt/docker/cadenza/.env` con permisos 600; nunca salen del servidor. Base de datos de producción nueva; la primera cuenta de investigador la crea el responsable con la CLI.

**Comprobación previa (2026-10-23).** Con un proyecto desechable en el servidor (`127.0.0.1:18380`, secretos generados allí y borrados después): servicios en `healthy` en 100 s, rutas de la interfaz y `/api/health` con 200, solo `127.0.0.1:18380` en escucha y 5432 y 8000 inaccesibles desde la IP de Tailscale. Simulando la `X-Forwarded-For` de Funnel desde el host, el límite de registro contó por esa IP (tres 201, un 429 y 201 desde otra IP). Que Funnel añada la cabecera tal como se espera se comprueba al publicar (#157).

**Segunda comprobación (2026-10-23), tras la revisión independiente**, con la subred fija y los límites de Nginx: sin cabecera, Nginx ve la pasarela `10.77.0.1`; una `X-Forwarded-For` con dos direcciones se resuelve a la última; una `X-Forwarded-For` enviada a la API desde otro contenedor no se cree; 25 accesos seguidos desde una IP dan 11 respuestas 401 y 14 respuestas 429, con las zonas del acceso y del registro separadas y las IPv6 agrupadas por /64; las rutas con caracteres de control responden 400; y en Chrome sin interfaz (1440 y 390 px) ninguna vista viola la política de seguridad de contenido. Las transcripciones simultáneas destaparon dos fallos anteriores, que se corrigen antes de publicar: HOMR no es seguro entre hilos ([#165](https://github.com/sebdavid3/Cadenza/issues/165)) y la API confirma la transacción después de responder ([#166](https://github.com/sebdavid3/Cadenza/issues/166)). El detalle está en `docs/infra/operacion_backend.md` §2.2.

## Consecuencias

### Positivas
- HTTPS válido y renovado sin tocar el router ni contratar nada.
- El host no expone ningún puerto nuevo fuera de `127.0.0.1`.
- La misma imagen web sirve para cualquier otra forma de exposición: basta con apuntar otro proxy al puerto local.

### Negativas / Riesgos
- El nombre `r2d2.tailcacb19.ts.net` queda público (aparece en los registros de transparencia de certificados) y la URL depende del nombre del tailnet.
- Funnel tiene límites de ancho de banda no documentados; sirve para una demostración y un uso moderado, no para tráfico alto.
- Configurar Funnel exige `sudo` en el servidor (no hay operador de Tailscale configurado): lo ejecuta el responsable.
- El servidor tiene 7,1 GiB de RAM compartidos con Immich; la API en CPU y PostgreSQL deben convivir con él.

## Alternativas consideradas

1. **Cloudflare Tunnel.** Descartado por ahora: exige un dominio gestionado en Cloudflare.
2. **Caddy con redirección de puertos.** Descartado: exige dominio, abrir puertos en el router y exponer la IP doméstica.
3. **Caddy como proxy interno en lugar de Nginx.** Equivalente; se elige Nginx por su imagen sin privilegios y porque su configuración de IP real (`real_ip`) es explícita.
