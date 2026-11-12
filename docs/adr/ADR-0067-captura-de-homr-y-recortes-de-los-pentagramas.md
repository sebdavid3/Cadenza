# ADR-0067: La captura de HOMR y los recortes de los pentagramas

- **Estado:** Aceptado
- **Fecha:** 2026-11-11
- **Decisores:** Responsable del proyecto (pidió el 2026-11-11 dejar lista la toma de datos para emparejar cada pentagrama de la foto con su transcripción corregida) y Equipo de Desarrollo
- **Relacionado:** [INV-0001](../investigaciones/INV-0001-salidas-internas-homr-bbox-y-confianza.md), [ADR-0028](ADR-0028-notas-sin-duracion-como-notas-de-adorno.md), [ADR-0054](ADR-0054-transcribir-sin-cuenta-desde-la-portada.md), [ADR-0060](ADR-0060-voz-por-encima-del-piano.md), [ADR-0065](ADR-0065-permiso-de-uso-de-los-datos-al-registrarse.md), [#103](https://github.com/sebdavid3/Cadenza/issues/103), [#403](https://github.com/sebdavid3/Cadenza/issues/403)

---

## Contexto

Un lector como HOMR se entrena con pares de una tira de pentagrama y su secuencia correcta. Cadenza guarda la foto (`sessions.image_artifact`) y la partitura corregida, pero no qué franja de la foto corresponde a qué compases:

- HOMR no da cajas por evento ni confianza (INV-0001). Sí detecta cada pentagrama, y esa caja se puede obtener.
- El `ScoreIR` no guarda dónde empieza cada sistema, y la importación descarta los `<print new-system="yes">` del MusicXML de HOMR.

Una prueba del 2026-11-11 sobre `TS-04` del banco (voz y piano, dos sistemas) confirmó que HOMR 0.7.0 tiene las dos piezas: `ProcessingConfig(write_staff_positions=True)` le hace llamar a `save_staff_positions` con sus pentagramas, y su MusicXML marca el sistema nuevo en el compás 4. Repartiendo las cajas de arriba abajo por sistema, cada tira recortada casaba con sus compases. La prueba enseñó también que:

- las cajas son relativas a la imagen que ve HOMR, que antes recorta el papel (`autocrop`) y la redimensiona;
- una página de voz y piano se lee dos veces (ADR-0060), y cada lectura da sus cajas;
- con el preprocesado de Cadenza encendido (apagado por defecto), HOMR ve otra imagen.

Reentrenar HOMR sigue fuera del alcance (#103). Esto solo deja la toma de datos lista.

## Decisión

1. **La captura viaja en el documento.** `ScoreDocument` gana un campo opcional, `omr_capture`: un objeto JSON opaco para el dominio, que no cuenta al comparar documentos y que `to_primitive` solo escribe si existe. Se guarda, por tanto, en `sessions.document` y en `previews.document`, y pasa sola de la vista previa a la sesión al reclamarla. No hace falta migración, y la API no la expone: `ScoreDocumentPayload` no la declara.
2. **Qué guarda la captura** (`format_version` 1, `cadenza.omr.adapters.homr_capture`):
   - `readings`: por cada lectura de HOMR, su modo (`paired` o `alone`), la forma de la imagen que vio HOMR (`image_shape`) y la de la que recibió (`source_shape`), el rectángulo del papel (`autocrop`, `[x, y, ancho, alto]`, o nulo si no recortó) y una caja por pentagrama (`cx`, `cy`, `w`, `h` relativos a la imagen de HOMR, y `grand` si es un gran pentagrama de piano).
   - `systems`: el número del primer compás de cada sistema, del MusicXML de HOMR de la lectura emparejada. La combinación de las dos lecturas del piano la escribe Cadenza y no lleva saltos de sistema.
   - `musicxml`: el MusicXML que escribió HOMR en cada lectura (`paired` y, en una página de voz y piano, `alone`), comprimido con zlib y en base64, con su sha256. Conserva lo que la importación descarta (trinos, grupetos, repeticiones, los sistemas). La combinación de las dos lecturas del piano la escribe Cadenza desde el `ScoreIR` y no se guarda: se rehace de la partitura. Si no se anotó ninguna lectura (un doble de pruebas), se guarda el MusicXML importado, como `importado`. `format_version` 2 (en la 1, de una versión previa que no llegó a `dev`, `musicxml` guardaba uno solo): una captura de otro formato queda fuera de los recortes con su motivo. En `TS-04` (medido el 2026-11-11), la captura entera ocupa 5,9 KB de un documento de 84 KB.
   - `homr_version`, `preprocessed` y `errors`.
3. **Cómo se captura.** El adaptador enciende `write_staff_positions` y envuelve dos funciones de `homr.main`, como ya envuelve otras piezas de HOMR (`homr_grand_staff`, `homr_progress`):
   - `save_staff_positions`: durante una captura anota las cajas y no escribe ningún archivo;
   - `autocrop`: anota el rectángulo, a partir del desplazamiento de la vista que devuelve dentro de la imagen.
   Fuera de una captura hacen lo de siempre, y sin captura (las evaluaciones de OMR-NED) `write_staff_positions` sigue apagado. Si la lectura del piano solo falla, se olvidan sus cajas. **La captura nunca hace fallar una transcripción:** un error (cajas no finitas, un recorte que no es una vista de la imagen, un MusicXML que no se lee) queda en `errors` o deja la sesión sin captura, con un aviso en el registro.
4. **Los recortes: `ml export-staves`** (`cadenza.learning.staff_strips` y `ml/export_staves_cli.py`), sobre una copia de la base y sus artefactos.
   - **Las tiras.** El sistema k va de su primer compás al anterior al siguiente. Las cajas, de arriba abajo, se reparten por sistema en el orden de las partes y sus pentagramas; un gran pentagrama ocupa dos pentagramas seguidos de una parte. Se prueba primero la lectura de pentagramas solos y después la emparejada, y vale la primera que casa exactamente. Las cajas se llevan a la foto (desplazamiento del papel y escala) y la tira llega hasta la mitad del hueco con el pentagrama vecino, como en HOMR.
   - **La salida:** un PNG por tira; `pentagramas.csv`, con su caja, sus compases y la transcripción de esos compases en la lectura (`lectura`) y en el estado final (`corregida`), y si difieren; los dos MusicXML de cada sesión; con `--laminas`, una lámina por sesión para comprobarlo a ojo; y `run_info.json` (commit, filtros, sesiones fuera con su motivo, recuentos, `"simulated": false`).
   - **Las sesiones:** por defecto solo las finalizadas y sin cuentas del registro público. Con `--include-self-registered` entran las del registro **con el permiso de uso de los datos vigente**, el del texto actual (`has_current_data_consent`; decisión del responsable del 2026-11-11, que da a ADR-0065 §7 su primer uso). Quedan fuera, con su motivo, las sesiones sin captura, sin imagen, preprocesadas, con errores en la captura, cuya foto no tiene la proporción de la imagen que leyó HOMR o cuyas cajas no casan; y cualquier otra que falle, sin parar la exportación.
   - **La foto se endereza como la vio HOMR:** HOMR la abre con OpenCV, que aplica la orientación EXIF, así que la exportación aplica `ImageOps.exif_transpose` antes de recortar.
   - **La salida** ha de estar vacía (lo de una exportación anterior, quizá de alguien que ya retiró su permiso, se quedaría) y no puede caer en `results/` ni en `data/` del repositorio.
5. **Desde la vista no se insertan ni se borran compases**, así que el compás N leído es el compás N final y la misma tira vale para la lectura y para la corrección.

## Consecuencias

### Positivas
- Cada transcripción nueva guarda lo necesario para formar los pares de entrenamiento de un lector, sin cambiar el `ScoreIR`, la importación, el contrato ni la web.
- La tabla de tiras compara, pentagrama a pentagrama, lo que leyó HOMR con lo que quedó, junto a su imagen: es la comparación que pedía el responsable.
- Comprobado en local el 2026-11-11, con HOMR 0.7.0 sobre `TS-04`: la sesión guarda las dos lecturas (4 y 6 cajas) y los sistemas `["1", "4"]`; `export-staves` da las 6 tiras; tras corregir una altura del compás 2 de la voz, solo esa tira sale como corregida. La prueba con HOMR real sobre la imagen del manifiesto del corpus también pasa.

### Negativas / Riesgos
- **Las sesiones anteriores no tienen captura.** Se podría rehacer volviendo a pasar HOMR sobre su imagen, que se guarda con la versión del motor; no se hace aquí.
- **El preprocesado** hace que las cajas no sean de la foto: esas sesiones quedan fuera de los recortes.
- **El reparto supone que HOMR detectó todos los pentagramas.** Si falta o sobra uno, las cajas no casan y la sesión queda fuera, con el motivo. No se intenta adivinar.
- **El primer compás de un sistema puede salir corrido.** HOMR marca el sistema nuevo en el compás que tiene abierto al acabar un pentagrama: si el pentagrama no acaba en una barra que haya detectado, ese compás empezó en el sistema anterior y se cuenta en el siguiente, y las tiras de los dos sistemas quedan corridas un compás. Un pentagrama que HOMR salta por vacío tampoco da salto de sistema. El recuento exacto de cajas solo atrapa algunos de estos casos; la lámina (`--laminas`) sirve para verlo.
- **La secuencia del CSV es un texto propio de Cadenza** (`F4:3/4`, `+` para una nota de acorde, `~` para la ligadura), no el vocabulario de HOMR. Convertirla al formato de entrenamiento es trabajo de #103; el MusicXML final de cada sesión ya queda escrito para eso.
- Un documento pesa unos KB más.

## Alternativas consideradas

1. **Una columna nueva o artefactos aparte.** Descartada por ahora: exigía una migración y llevar la captura por la transcripción, la cola de trabajos, la vista previa y su reclamación. El documento ya hace ese camino.
2. **El MusicXML de HOMR como artefacto.** Descartada por lo mismo; comprimido, cabe en el documento.
3. **Leer el `.txt` que escribe HOMR.** Descartada: envolver `save_staff_positions` da lo mismo sin pasar por el formato de texto ni dejar archivos.
