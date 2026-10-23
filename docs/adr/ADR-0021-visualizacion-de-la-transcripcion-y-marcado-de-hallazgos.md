# ADR-0021: Visualización de la transcripción y marcado de hallazgos por compás

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Dirección del proyecto Cadenza (decisión aprobada por el responsable el 2026-10-23), Equipo de Desarrollo
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0011](ADR-0011-semantica-de-anclas-ante-ediciones.md), [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md), [ADR-0019](ADR-0019-base-del-cliente-web.md), [INV-0001](../investigaciones/INV-0001-salidas-internas-homr-bbox-y-confianza.md)

---

## Contexto

La Fase 8 añade una vista de solo lectura de una sesión (`/sesiones/:id`, [#153](https://github.com/sebdavid3/Cadenza/issues/153)): la partitura digitalizada, la imagen original y los hallazgos del validador. No es la vista de corrección. Había que decidir si los hallazgos se marcan sobre la notación y con qué granularidad.

Restricciones conocidas:

- HOMR devuelve siempre `bbox: null` (INV-0001): no se puede marcar nada sobre la imagen original.
- El validador tiene, medido sobre PrIMuS (`exp_06`), una precisión del 64,52 % y un recall del 39,80 %: un hallazgo es un posible error y su ausencia no garantiza que el compás esté bien.
- Las reglas no anclan igual. `measure.balance` (duración del compás) y el cambio de armadura de `key.consistency` anclan al **primer evento del compás** porque el problema es del compás entero; `pitch.range`, `tie.resolution` y `voice.collision` anclan al evento.

Spike del 2026-10-23 con OSMD 2.2.1 sobre las 45 sesiones de la base local (HOMR en GPU, incipits de PrIMuS): las 45 se renderizan; el número de compases de OSMD coincide con el del `ScoreIR` en las 45 y los 32 hallazgos (todos `measure.balance`) se sitúan en su compás. A nivel de evento, con el exportador anterior a [#152](https://github.com/sebdavid3/Cadenza/issues/152) se alineaban 654 de 657 eventos (fallaban en un compás sobrellenado que el exportador alteraba); con el exportador fiel de #152, los 681.

Opciones: (a) sin marcas, solo la lista; (b) compases con hallazgos marcados, más la lista; (c) el evento exacto, más la lista.

## Decisión

Se adopta **(b): se marca el compás de cada hallazgo y se lista cada hallazgo**.

1. **Granularidad de compás.** La marca cubre el compás del ancla (`anchor.measure` en el pentagrama `anchor.staff`), con la trama de puntos violeta y el contorno violeta del «compás dudoso» de `DESIGN.md`. No se marca el evento: para `measure.balance` señalaría un evento inocente (casi siempre un silencio o la primera nota), que es justo lo que no debe sugerir una vista de solo lectura. La precisión por evento corresponde a la vista de corrección, que necesita seleccionar símbolos.
2. **Correspondencia ancla→compás.** El compás se busca por posición en el pentagrama del `ScoreIR` materializado (el índice del compás con ese número) y se toma el compás gráfico de OSMD con ese índice. Si OSMD no produce el mismo número de compases que el `ScoreIR`, no se dibuja ninguna marca y la vista lo dice: la lista sigue siendo la referencia.
3. **Qué hallazgos.** Los de la última validación (`latest_only=true`, que filtra por `validated_at_seq`), no `at_seq`: la vista muestra el estado actual. Los descartados se piden (`include_dismissed=true`) pero no se marcan en la partitura; se cuentan y se pueden desplegar en la lista, con su motivo. Si los hallazgos son de un estado anterior al actual (`at_seq < current_seq`), la vista lo avisa.
4. **Lenguaje honesto.** Siempre «posible error» y nunca «error» a secas; la severidad no se muestra como certeza. La vista avisa de que el validador no lo detecta todo y de que no ver ningún posible error no garantiza que la transcripción sea correcta. No muestra las cifras de precisión ni de recall.
5. **Render.** OSMD 2.2.1 sobre el MusicXML de `GET /sessions/{id}/export?format=musicxml`, cargado bajo demanda (un fragmento propio de unos 1,4 MB, 362 kB comprimido) para no pesar en las demás rutas, sin título, compositor ni nombres de parte y sin agrupar silencios de compás (`autoGenerateMultipleRestMeasuresFromRestMeasures: false`), que rompería la correspondencia de compases. Las marcas abarcan la altura del pentagrama con un margen fijo, de modo que todas las de un sistema miden lo mismo. Si la partitura no se puede renderizar, la imagen y la lista siguen visibles.
6. **Dependencia.** OSMD declara `gl` (WebGL sin interfaz, para generar imágenes en Node) como dependencia opcional con un script de instalación; el navegador no la usa y npm no ejecuta ese script.

## Consecuencias

### Positivas
- La marca no promete más precisión de la que el validador tiene: dice «revisa este compás», que es lo que las reglas saben.
- La correspondencia por compás es robusta: no depende de cómo OSMD agrupa acordes, voces o figuras que no caben en una sola nota.
- El mapa ancla→SVG por evento (ADR-0006) queda acotado a la vista de corrección, con el exportador ya fiel (#152).

### Negativas / Riesgos
- Para las reglas que anclan al evento (`pitch.range`, `tie.resolution`, `voice.collision`) se pierde la nota concreta en la partitura; el mensaje de la lista la describe.
- Depende de que OSMD conserve un compás gráfico por compás del MusicXML; si una versión futura lo cambia, la vista deja de marcar y lo avisa en lugar de marcar mal.

## Alternativas consideradas

1. **(a) Sin marcas.** Descartada: obliga a contar compases para encontrar el señalado, y la correspondencia por compás es fiable.
2. **(c) Evento exacto.** Descartada para esta vista: con `measure.balance`, la regla más frecuente, señala el primer evento del compás y no al culpable.
