# ADR-0072: SMB y MUSCIMA++ en los datos de los errores de HOMR

- **Estado:** Aceptado
- **Fecha:** 2026-11-19
- **Decisores:** Responsable del proyecto (metió SMB y MUSCIMA++ en la Fase 12 el 2026-11-19, en [#102](https://github.com/sebdavid3/Cadenza/issues/102), y decidió ese mismo día no esperar el acceso a SMB) y Equipo de Desarrollo
- **Relacionado:** [INV-0003](../investigaciones/INV-0003-smb-y-muscima.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0066](ADR-0066-homr-en-la-gpu-de-produccion.md), [ADR-0068](ADR-0068-tablas-y-recortes-en-una-sola-exportacion.md), [#255](https://github.com/sebdavid3/Cadenza/issues/255), [#418](https://github.com/sebdavid3/Cadenza/issues/418)

---

## Contexto

Los datos de los errores de HOMR salen hoy solo de PrIMuS (`exp_12`, #255): música impresa, sintética y de una voz. El responsable decidió sumar SMB (páginas reales escaneadas, con piano) y MUSCIMA++ (manuscritas). Ninguno trae la partitura en un formato que Cadenza ya use para su verdad:

- **SMB** trae **kern por región (pentagrama o sistema), que `packages/interchange` lee, pero el acceso es restringido con aprobación manual y no hay datos todavía.
- **MUSCIMA++** trae un grafo de símbolos (MuNG), no una partitura: la altura y la duración hay que inferirlas, y el formato no anota las voces.

[INV-0003](../investigaciones/INV-0003-smb-y-muscima.md) recoge qué trae cada uno, su licencia y lo medido.

## Decisión

1. **Dos experimentos nuevos, sin tocar `exp_12` ni `exp_14`.** `exp_16_muscima_homr.py` (MUSCIMA++) y `exp_17_smb_homr.py` (SMB) siguen las fases de `exp_12` (preparar con manifiesto y sha256, transcribir de forma reanudable, medir y escribir al final) y comparten `ml/experiments/external_corpus.py`: la transcripción (la de `exp_12`, copiada para no cambiarla), la derivación y verificación de las correcciones, la SER y el OMR-NED. Escriben archivos nuevos en `results/`, con su `run_info`.
2. **El corpus de correcciones lleva su origen y su obra.** Los registros tienen el formato de `build_correction_records` más `source` (`muscima` o `smb`) y `work_id` (`muscima-N-<página>`, las 7 copias de una misma página; `smb:<original_score>`, las regiones de una misma obra). La partición es la de #255 (`assign_split` sobre la obra, con la semilla por defecto). `ml export-tables --corpus` los lee sin cambios: ya tomaba `source` y `work_id` del registro.
3. **La unidad.** En SMB, la **región** recortada de la página (como el incipit de `exp_12`): la verdad de SMB es por región. En MUSCIMA++, la **página**: su anotación es por página.
4. **La verdad de MUSCIMA++ se infiere y solo donde se puede.** `cadenza.learning.muscima` lee MuNG con la biblioteca estándar y convierte a `ScoreIR` las páginas de **un pentagrama por sistema y una voz**, con la regla de la posición en el pentagrama de la inferencia de referencia de `mung` (MIT). Rechaza, con su motivo, los sistemas de varios pentagramas, la polifonía, los compases abreviados (`multiMeasureRest`, `repeat1Bar`) y la clave de do que no se puede situar en una línea. De las demás páginas se mide la tasa de fallos y cuántas notas lee HOMR frente a las cabezas anotadas. La calidad de la verdad inferida se mide aparte, sin HOMR: compases que suman lo que pide su compás y SER entre las versiones de una misma página de copistas distintos.
5. **HOMR en la GPU, como en producción (ADR-0066), sin preprocesado.** Las imágenes de CVC-MUSCIMA son blanco sobre negro y se invierten antes de pasarlas a HOMR; es lo único que se les hace y queda en el manifiesto. `exp_12` se midió en CPU: el dispositivo va en cada `run_info`.
6. **Las descargas las autoriza el responsable** con nombre, origen y tamaño, y van a `data/` (sin versionar). SMB necesita además que el responsable pida el acceso con su cuenta; mientras no lo haga, `exp_17` queda sin ejecutar y `pyarrow`, que solo hace falta para leer su parquet, no entra en las dependencias.
7. **Las correcciones se cuentan solo con los compases alineados.** `derive_edit_events` empareja compases por su posición y no corrige cuántos hay: donde HOMR lee otro número de compases, sus correcciones son de alineación. La distribución de correcciones se da solo para las imágenes o regiones con el mismo número de compases; la SER y el OMR-NED, que no dependen de alinear compases, se dan para todas. Un fallo del OMR-NED se registra aparte y no descarta lo derivado.
8. **La capa de sugerencias no se reentrena con estos corpus.** `exp_14` y el modelo siguen con PrIMuS; mezclar corpus es una decisión aparte, con su medición.

## Alternativas consideradas

- **Convertir toda MUSCIMA++ a `ScoreIR`, polifonía incluida.** MuNG no anota las voces y la inferencia de referencia no ordena los ataques en música polifónica (`Cannot deal with onsets in polyphonic music yet`). Asignar voces por la dirección de las plicas sería una verdad inventada por Cadenza para medir a HOMR. Descartado.
- **Medir SMB por página, como el banco de HOMR.** La verdad de SMB es por región y unir varias regiones en un solo **kern no es trivial; la página mezclaría la lectura de cada sistema con la de su orden. Descartado para el corpus; se puede añadir después como medición aparte.
- **Instalar el paquete `mung`.** Trae `scikit-image` y sus dependencias para leer un XML: la lectura y la regla de la altura caben en un módulo de la biblioteca estándar.

## Consecuencias

- Los datos de los errores de HOMR cubren, además de PrIMuS, música manuscrita (en el subconjunto convertible) y, cuando haya acceso, páginas reales escaneadas.
- Las cifras de MUSCIMA++ describen 20 páginas de música, no 140: las 7 versiones de una página son la misma música.
- `exp_17` está probado con datos de ejemplo, no con SMB: la primera ejecución real debe empezar por un piloto (`transcribe --limit`) y revisar el recorte.
