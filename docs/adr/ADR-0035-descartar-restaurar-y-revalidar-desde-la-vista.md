# ADR-0035: Descartar, restaurar y revalidar los posibles errores desde la vista

- **Estado:** Aceptado
- **Fecha:** 2026-10-24
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0012, ADR-0013, ADR-0014, ADR-0019, ADR-0021, ADR-0030, ADR-0031, ADR-0032 y ADR-0034, CLAUDE.md §9)
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md), [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md), [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0030](ADR-0030-correccion-de-altura-duracion-y-alteracion.md), [ADR-0031](ADR-0031-marcas-de-notacion-en-el-score-ir.md), [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md), [ADR-0034](ADR-0034-deshacer-y-rehacer-desde-la-vista.md), [#186](https://github.com/sebdavid3/Cadenza/issues/186)

---

## Contexto

La vista de una sesión lista los posibles errores de la última validación, marca su compás y avisa si la validación es de un estado anterior (ADR-0021), pero no deja actuar sobre ellos. La API ya lo tiene todo (frontend-handoff §3). Hechos comprobados en el código y contra la API real con HOMR el 2026-10-24:

- `POST /sessions/{id}/findings/{finding_id}/dismiss` con `{"reason"?}` y `.../restore` responden 200 con el hallazgo; 409 si la sesión está finalizada (es el único 409 de estas rutas); 404 si el hallazgo no está; 403 a un investigador ante una sesión ajena. El motivo es texto libre (`Text`, sin límite).
- `POST /sessions/{id}/validate` revalida el estado actual del **servidor** y responde con su `current_seq` y **solo los hallazgos activos**. Revalidar el mismo estado sustituye sus hallazgos **con otros id** (idempotencia por `(session_id, at_seq)`, ADR-0013): en la prueba, 42–46 pasaron a 174–178. Un descarte se conserva si su evento no cambió (#36). Un investigador puede revalidar cualquier sesión (ADR-0013 §4).
- `SessionDetailRead` no expone `validated_at_seq`: sin hallazgos no se sabe de qué estado es la última validación (ADR-0021 §3).
- Con varias voces, `measure.balance` señala cada voz del compás por separado y `voice.collision` cada evento (ADR-0032): en *Mondnacht* (38 posibles errores en 28 compases) hay compases con dos «Duración del compás» y otros con dos «Voces que se pisan» de mensaje idéntico.

## Decisión

1. **Quién.** Descarta, restaura y revalida quien transcribió la sesión mientras no esté finalizada: las mismas condiciones que corregir (ADR-0030). Para los demás el panel sigue en solo lectura, **también para un investigador ante una sesión ajena aunque la API le deje revalidar**: revalidar añade una validación al historial de hallazgos de la sesión (ADR-0013), que el estudio de esfuerzo lee (D38), en un momento que su autor no eligió; y descartar o restaurar le responde 403.
2. **Se descarta cada posible error, no el compás.** Bajo cada compás de la lista, un «Descartar» por posible error. Con varios en el compás (uno por voz, por ejemplo), la lista y los botones los numeran («1 · Duración del compás», «Descartar 1») y cada botón tiene por descripción accesible el mensaje del suyo. El nombre dice qué y dónde: «Descartar como falso positivo · Duración del compás, compás 3» (con varios pentagramas, «… del pentagrama 2», en el orden global de las marcas).
3. **El motivo es opcional.** El botón abre debajo un formulario (`aria-expanded`, foco en el campo): un campo de una línea, «Descartar como falso positivo» y «Cancelar»; Esc lo cierra y devuelve el foco al botón. Se envía recortado, y en blanco como `null`. El campo admite hasta 500 caracteres: la API no pone límite y el motivo se lee en una lista.
4. **Lenguaje honesto (ADR-0021 §4).** El formulario dice antes de enviarlo que descartar no corrige la partitura: el compás deja de señalarse y sus notas siguen igual. El aviso del panel lo repite para quien puede descartar. Tras descartar, «… La partitura no cambia.». Cuando no queda ningún posible error activo, la vista y el anuncio dicen que eso no garantiza que la transcripción esté bien.
5. **Nada se da por hecho sin el 200.** No hay actualización optimista. El hallazgo devuelto sustituye al de la lista en la caché de todos los estados, también si la vista se cerró mientras tanto; si la vista se cerró sin respuesta, la lista se da por vieja y se vuelve a pedir al volver. Descartar y restaurar no piden el detalle ni el MusicXML: no cambian la partitura.
6. **Revalidar es explícito** (ADR-0013): un botón «Revalidar» cuando la validación es de un estado anterior al que se ve, o cuando no se sabe (sin hallazgos y con ediciones); no se revalida solo tras cada edición, porque cada revalidación escribe una validación en el historial que leen las métricas y la persona decide cuándo ha terminado de corregir. El botón espera mientras se guarda una corrección. Con la respuesta, su `current_seq` dice qué se validó:
   - el estado que se ve: se vuelve a pedir la lista (la respuesta no trae los descartados que se conservan), y las marcas y la lista pasan a ser las de ese estado;
   - uno posterior (se editó en otra pestaña): se carga ese estado entero, como al recargar tras un 409 (`reload` del editor), y se dice;
   - uno anterior (se editó mientras se revalidaba): se dice que hay que volver a revalidar, y el botón sigue.
7. **El estado validado que se conoce.** Sin hallazgos, el `current_seq` de la última revalidación hecha en la pestaña se guarda en la caché de la sesión (`validatedSeqQuery`) y cuenta con los `at_seq` de la lista: tras revalidar sin hallazgos, la vista dice «El validador no señala ningún compás en la partitura actual.» en lugar de «puede que no esté al día». No cambia el contrato.
8. **Una orden a la vez.** Mientras se descarta, se restaura o se revalida, las demás acciones del panel esperan (`aria-disabled`): revalidar sustituye los hallazgos y sus id.
9. **Errores.** Un 409 dice que la sesión está finalizada y la recarga, que pasa a solo lectura. Un 404 dice que ese posible error ya no está en la última validación y vuelve a pedir la lista (si tampoco está la sesión, la vista lo dice como siempre). El 403 tiene su mensaje. Sin respuesta (red, tiempo agotado, 5xx) se dice que no se sabe si se hizo y que se puede volver a intentar: repetirlo no cambia nada. El formulario sigue abierto con el motivo. Lo que pasó se dice en una región `aria-live` bajo el título del panel; dos mensajes iguales seguidos se vuelven a anunciar.
10. **Foco.** Tras descartar, al «Descartar» del posible error siguiente (o del anterior; sin ninguno, al título del panel). Tras restaurar, al «Descartar» del restaurado, ya entre los activos. Tras revalidar, al botón si sigue y, si desaparece, al título.
11. **Marcas.** Siguen siendo por compás (ADR-0021) y se calculan con la lista nueva sobre la partitura del estado que se ve, así que no dependen de las marcas de notación (ADR-0031) ni de las voces (ADR-0032): varios posibles errores de un compás son una marca y una entrada numerada de la lista.

## Consecuencias

### Positivas
- Se descarta, se restaura y se revalida con el ratón, el dedo o el teclado, sin cambios en el contrato ni en el backend. Verificado contra la API real con HOMR (incipits de PrIMuS, una melodía con staccatos y acentos y la página 9 de *Mondnacht*, transcritos en local) a 1440 y 390 px: un descarte con motivo y su restauración con Intro; tras cuatro ediciones, «Revalidar» quitó la marca del compás corregido y conservó el descarte de otro cuya nota no cambió; deshacer volvió a dejar la validación atrás y revalidar trajo de vuelta el posible error con su mensaje nuevo; en *Mondnacht*, alargar la segunda voz de un compás y revalidar añadió su posible error y su marca (29 marcas, 39 posibles errores); una edición hecha por la API mientras la vista estaba atrás hizo que revalidar cargara el estado nuevo; un 404 real (otra revalidación cambió los id) y un 409 real (sesión finalizada); un investigador ante una sesión ajena, en solo lectura.
- El descarte queda en el servidor con su autor y su motivo, y el log de ediciones no cambia.

### Negativas / Riesgos
- El estado validado conocido es de la pestaña: tras recargar una sesión sin posibles errores y con ediciones, la vista vuelve a decir que no sabe si la validación está al día (D64). Exponer `validated_at_seq` en `SessionDetailRead` (un campo nuevo, compatible) lo resolvería.
- Cada revalidación añade una validación al historial de hallazgos (ADR-0013): las métricas de esfuerzo ([#188](https://github.com/sebdavid3/Cadenza/issues/188), D38) tendrán que decidir cómo cuentan las revalidaciones y los descartes.
- La marca cubre la altura del pentagrama con un margen fijo (ADR-0021 §5): una nota con líneas adicionales y su staccato pueden asomar unos píxeles por debajo de ella (4 px en la melodía de prueba). No es nuevo de esta decisión.

## Alternativas consideradas

1. **Revalidar solo tras cada edición.** Descartada: llena el historial de validaciones intermedias que nadie pidió y hace esperar cada corrección; ADR-0013 deja la revalidación bajo demanda.
2. **Descartar el compás entero.** Descartada: con varias voces un compás tiene varios posibles errores, y descartar uno no dice nada de los otros.
3. **Añadir `validated_at_seq` al detalle de la sesión.** Aplazada: es un cambio del contrato, aunque compatible, y el issue es de la web; queda como D64.
