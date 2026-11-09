# ADR-0062: Despliegue continuo desde `main` en el homelab, con el servidor tirando de GitHub

- **Estado:** Aceptado (se activa tras el estudio y la promoción de #261)
- **Fecha:** 2026-11-04
- **Decisores:** Responsable del proyecto y Equipo de Desarrollo (compatible con ADR-0023 y ADR-0029, CLAUDE.md §5)
- **Relacionado:** [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md), [#337](https://github.com/sebdavid3/Cadenza/issues/337), [#261](https://github.com/sebdavid3/Cadenza/issues/261), [#252](https://github.com/sebdavid3/Cadenza/issues/252), [#157](https://github.com/sebdavid3/Cadenza/issues/157), [#174](https://github.com/sebdavid3/Cadenza/issues/174), [#205](https://github.com/sebdavid3/Cadenza/issues/205)

---

## Contexto

- El despliegue público del homelab (#157, `operacion_backend.md` §2.2) es un clon de `dev` en `/opt/docker/cadenza` que se actualiza a mano: copia, `git pull`, `up -d --build` y limpieza. `https://cadenza.sebdavid.dev` llega al mismo servicio por un túnel de Cloudflare, además de Funnel.
- La CI (`ci.yml`) prueba y construye las imágenes en cada push a `dev` y `main`, pero no despliega.
- Tras el estudio, `dev` se promueve a `main` (#261) y producción debe seguir a la rama estable, no a la de integración.
- El repositorio es público. Un runner autoalojado en el servidor ejecutaría flujos que cualquiera puede proponer en un PR, y desplegar desde GitHub por SSH obliga a abrir una entrada al homelab y a guardar una clave en los secretos del repositorio.

## Decisión

1. **El servidor tira, GitHub no empuja.** `deploy/despliegue-continuo.sh` corre en el cron del servidor cada 5 minutos con el usuario del despliegue. No hay runner autoalojado ni conexión entrante, y GitHub no guarda credenciales del servidor: solo hace falta `gh` autenticado en el servidor para leer el estado de la CI.
2. **Producción sigue a `main`.** El script trae `origin/main` y solo avanza en *fast-forward*: si `main` se reescribe o el servidor tiene commits propios, se detiene. Si el árbol tiene cambios sin comitear (un arreglo hecho a mano), también se detiene, para no pisarlos.
3. **Solo con la CI en verde.** Se mira la ejecución más reciente del flujo `CI` lanzada por el push del commit a `main` (`/actions/runs`), no los *check runs* sueltos: la ejecución solo termina cuando acaban todos sus jobs, y las apps de terceros no cuentan. En curso, en cola o sin empezar, se espera a la siguiente pasada. Terminada sin éxito (`failure`, `cancelled`, `timed_out`...), no se despliega y se dice una vez, pero el commit no se descarta: si se relanza y pasa, se despliega.
4. **Copia antes, salud después.** Antes de tocar nada, una copia con el servicio `backup`, verificada y con el commit en el nombre (`cadenza-<fecha>-antes-<sha>.tar.gz`). Después, `up -d --build`, la imagen de copias reconstruida y una espera de hasta 5 minutos a que `/api/health` responda con la base de datos conectada (HOMR tarda hasta 2 minutos en cargar).
5. **Vuelta atrás automática solo del código.** Si la API no queda sana, el script vuelve al commit anterior, reconstruye, marca el nuevo como descartado (en `rechazados`, de donde se quita a mano para reintentarlo) y avisa. La API aplica las migraciones al arrancar, así que si la versión nueva ya migró la base, la anterior puede no arrancar: entonces el script lo dice («ERROR GRAVE»), señala la copia que hay que restaurar a mano (§4.2), avisa y se pone en pausa. No se automatiza `downgrade()`: una restauración a mano es más segura que una migración inversa sin supervisión.
6. **Lo que necesita a una persona, pausa y avisa.** Si la copia previa falla o no se verifica, si el checkout falla o si tampoco arranca la versión anterior, el script escribe el motivo en el archivo de pausa y llama al comando de aviso (`CADENZA_DESPLIEGUE_AVISO`, opcional, con el mensaje como argumento): no insiste cada 5 minutos. Antes de la copia comprueba además que ningún archivo sin seguimiento del servidor choque con el commit nuevo.
7. **Silencioso cuando no hay novedad.** Una pasada sin cambios, con la CI en curso o en pausa no escribe nada, para no llenar el log cada 5 minutos. Un error que se repetiría en cada pasada se registra una vez.
8. **Pausa sin tocar el cron.** El archivo `pausado` en el directorio de estado (`~/.local/state/cadenza-despliegue/` por defecto) detiene el despliegue continuo. `--simular` dice qué haría sin cambiar nada ni callar los errores de la pasada real. El puerto de la salud se lee del `.env`, que el cron no carga.
9. **Fuera del estudio.** No se activa durante el congelado (#252) ni antes de la promoción (#261): con `main` atrasado, avanzar a `main` sería volver atrás un mes. Para que el primer paso de `dev` a `main` sea un *fast-forward*, la promoción se hace con un merge (o en *fast-forward*), no con *squash*; si no, ese primer paso se da a mano (`git checkout -B main origin/main` tras la copia).

## Alternativas descartadas

- **Runner autoalojado de GitHub Actions en el servidor:** en un repositorio público, ejecuta código ajeno con acceso a Docker en el homelab.
- **Un job de despliegue que entre por SSH (Tailscale o Cloudflare Access):** abre una entrada al servidor y guarda una credencial en los secretos del repositorio. Para un solo servidor, que el servidor consulte es más simple.
- **Watchtower o un registro de imágenes:** la API y la web se construyen en el servidor desde el código (`up -d --build`), y la copia previa y la espera a la salud no encajan en un actualizador de imágenes.

## Consecuencias

- Fusionar en `main` es desplegar: la promoción de `dev` a `main` (#261) pasa a ser el acto de publicar.
- Un despliegue fallido deja producción en la versión anterior y el commit descartado anotado en el estado; el log del cron (`backups/despliegue.log`) dice qué pasó.
- Las pruebas del script (`deploy/tests/`, 28 casos) usan git de verdad y `docker`, `gh` y `curl` falsos; el `gh` falso aplica con `jq` el filtro real del script sobre ejecuciones con la forma de la API de GitHub. `deploy` entra en los `testpaths` de pytest.
