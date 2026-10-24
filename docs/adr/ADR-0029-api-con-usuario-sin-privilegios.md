# ADR-0029: La API corre con un usuario sin privilegios

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0015 y ADR-0023, CLAUDE.md §9)
- **Relacionado:** [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md), [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md), D57, [#156](https://github.com/sebdavid3/Cadenza/issues/156), [#159](https://github.com/sebdavid3/Cadenza/issues/159), [#192](https://github.com/sebdavid3/Cadenza/issues/192)

---

## Contexto

La imagen de la API (`Dockerfile`) no definía un usuario: la API corría como root en su contenedor (D57). El despliegue lo mitigaba con `cap_drop: ALL`, `no-new-privileges` y sin puertos publicados (ADR-0023), pero cualquier fallo de la API o de HOMR actuaba como root sobre el sistema de archivos del contenedor y sobre el volumen de artefactos.

Medido el 2026-10-23 en el servidor del despliegue, con una imagen de prueba sin root y las restricciones del despliegue:
- **Escrituras de HOMR al transcribir un incipit de PrIMuS.** Escribe su directorio de trabajo en `/tmp` (lo crea el adaptador y lo borra al terminar), un registro vacío en `/tmp` y el identificador de dispositivo de ONNX Runtime en `~/.cache/Microsoft/DeveloperTools/.onnxruntime`. Los pesos están en la imagen desde el build (`homr --init`): `download_weights` los encuentra y no escribe nada.
- **Caché de bytecode.** Como root, la API escribía también la de los paquetes del workspace en `/app/packages`. uv los instala en modo editable y no los compila (`UV_COMPILE_BYTECODE` solo compila `site-packages`).
- **Volumen del despliegue.** El de artefactos (`artifacts_data`) es de root: lo creó Docker al montarlo en una imagen sin esa carpeta. Con la imagen sin root, la API lo lee pero no escribe en él (`Permission denied`).
- **`/health`.** Respondía 200 de todos modos: en producción el almacén no se inyecta y `/health` no comprobaba la carpeta. La API habría arrancado sana para fallar en la primera transcripción.
- **Copias.** La restauración de copias (#159) corre como root y crea las carpetas de artefactos que faltan: serían de root.

## Decisión

1. **Usuario propio con UID y GID fijos.** La etapa final de la imagen crea el usuario `cadenza` (UID y GID 10001, sin shell, HOME en `/home/cadenza`) y arranca con `USER cadenza`.
   - El código sigue siendo de root y solo se lee.
   - `/app/data/artifacts` es de `cadenza`. Un volumen nuevo hereda ese dueño al montarse por primera vez.
   - El número es fijo para poder nombrarlo en la migración.
2. **Bytecode compilado en el build.** `python -m compileall` compila `/app/apps` y `/app/packages`, que el usuario de la API no puede escribir.
3. **Sin arranque como root.** No hay un entrypoint que corrija permisos y después cambie de usuario: necesitaría las capacidades `CHOWN`, `SETUID` y `SETGID`, que el despliegue quita (`cap_drop: ALL`).
4. **La migración de un volumen existente es un paso aparte, una sola vez.** Un contenedor desechable de la misma imagen, como root y sin las restricciones del servicio, da el volumen al usuario de la API:

   ```bash
   docker run --rm --user 0 --entrypoint chown -v cadenza-prod_artifacts_data:/app/data/artifacts cadenza-api:prod -R 10001:10001 /app/data/artifacts
   ```

   El procedimiento está en `docs/infra/operacion_backend.md` §2.2.
5. **`/health` comprueba que la API puede escribir sus artefactos.** Si no hay almacén inyectado, comprueba `artifacts_dir`, la carpeta de producción. Sin permiso de escritura responde 503 con `artifact_store: "error"` y deja en el registro la carpeta afectada. El healthcheck de Compose marca entonces la API como `unhealthy`. El contrato de `/health` no cambia: los mismos campos y valores.
6. **La restauración da los artefactos al dueño de su carpeta.** Si corre como root, `restore` pasa todo lo que hay bajo la carpeta de artefactos al dueño de esa carpeta. Sin ser root no hace nada: lo restaurado ya es de quien restaura.
7. **La CI transcribe un íncipit dentro de la imagen.** Usa las restricciones del despliegue y el sistema de archivos de solo lectura salvo `/tmp` y el HOME del usuario. El íncipit es propio del proyecto (`apps/api/tests/fixtures/incipit.musicxml`), dibujado con Verovio como PrIMuS. Su imagen se versiona porque el corpus no está en el repositorio. Si HOMR necesitara escribir en otro sitio, la CI fallaría.

## Consecuencias

### Positivas
- La API ya no corre como root.
- Un volumen mal configurado se ve en `/health` y en `docker compose ps`, y no en la primera transcripción.
- Restaurar una copia ya no deja carpetas en las que la API no pueda escribir.
- Medido el 2026-10-23 en el servidor, con una imagen construida desde esta rama:
  - El paso de la CI transcribe las 14 alturas del íncipit.
  - Un volumen de root sin migrar da `/health` 503 («la API no puede escribir en /app/data/artifacts»), y tras la migración, 200.
  - Una restauración como root deja los artefactos y sus carpetas con UID 10001, y la API escribe en ellas.

### Negativas / Riesgos
- **Migración manual.** Actualizar un despliegue existente exige la migración del volumen una vez. Sin ella, la API arranca `unhealthy` y no transcribe.
- **UID fijo.** Si otra imagen escribe en el mismo volumen con otro usuario, hay que alinearlo. Es el caso del plano offline (`Dockerfile.ml-cuda`, perfil `batch` del compose de desarrollo), que hoy no se construye (D53).
- **Copias de root.** Las copias que escribe el servicio `backup` en el host siguen siendo de root. No cambia: ese contenedor sigue corriendo como root para leer y restaurar.
- **Imagen de producción.** El íncipit de la CI y su script viajan en ella, porque el builder copia `apps/api` entero. Son unos 14 KB.

## Alternativas consideradas

1. **Entrypoint como root que hace `chown` y baja a `cadenza` con `gosu` o `setpriv`.** Descartada: devuelve al contenedor capacidades que el despliegue quita.
2. **UID asignado por `useradd` sin fijar.** Descartada: el número podría cambiar entre versiones de la imagen base, y la migración no sabría a quién dar el volumen.
3. **Montar el volumen con otro dueño desde Compose.** Descartada: los volúmenes locales de Docker no tienen esa opción, y `user:` en Compose sin usuario en la imagen no tendría HOME para ONNX Runtime.
