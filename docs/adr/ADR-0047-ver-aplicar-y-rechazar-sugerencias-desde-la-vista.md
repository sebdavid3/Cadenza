# ADR-0047: Ver, aplicar y rechazar las sugerencias de la capa desde la vista

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0011, ADR-0012, ADR-0021, ADR-0027, ADR-0030, ADR-0033, ADR-0034, ADR-0035, ADR-0036, ADR-0037, ADR-0038 y ADR-0040, CLAUDE.md §9 y §10)
- **Relacionado:** [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md) (§5 y enmiendas 18 y 19), [ADR-0040](ADR-0040-catalogo-de-reglas-y-mensajes-en-lenguaje-musical.md) (§2 y §13), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md), [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md), [#258](https://github.com/sebdavid3/Cadenza/issues/258), [#256](https://github.com/sebdavid3/Cadenza/issues/256), [#244](https://github.com/sebdavid3/Cadenza/issues/244), [#188](https://github.com/sebdavid3/Cadenza/issues/188)

---

## Contexto

La capa de sugerencias (#256, ADR-0036) ya deja en cada posible error de 0 a 3 `suggestions` (`SuggestionRead`), la ruta de rechazo y el `suggestion_id` de una edición, con el 409 `stale_suggestion` detrás del 409 de `base_seq`. Por decisión del responsable (enmienda 19) el servidor solo muestra, en la condición asistida, las sugerencias de alteración de confianza alta. La web no enseñaba nada de esto: el panel de posibles errores solo mostraba la regla, el mensaje y «Qué revisar», que no se muestra en los `learned.*` porque su `suggested_fix` es la edición propuesta (ADR-0040 §2). La enmienda 18 deja a #258 y a #244 qué hacer con un `learned.*` cuya sugerencia se rechazó.

Lo que no se toca: el `base_seq` del estado que se ve y el 409 sin reintento (ADR-0011), sin actualización optimista (ADR-0030, ADR-0034), una edición en un solo viaje (ADR-0037), la orden en espera de ADR-0038, revalidar solo bajo demanda (ADR-0035) y nada del validador en la condición no asistida (ADR-0040 §13).

## Decisión

1. **Dónde se ven.**
   - **En el panel de posibles errores**, bajo cada posible error que tiene sugerencias, una por bloque: la explicación que da el servidor (`explanation`, en lenguaje musical, con la evidencia «en N de M casos parecidos») y la confianza **en palabras** («Confianza alta», «Confianza media»), nunca en porcentaje.
   - **En la barra de corrección**, si la nota elegida es la que cambia alguna sugerencia de un posible error activo, el grupo «Sugerencias para esta nota», encima de los controles. El ancla de la sugerencia es relativa al estado de su validación: se lleva al estado que se ve con la regla de desplazamiento (ADR-0011 §2) para saber si es de esa nota.
   - En solo lectura (una sesión ajena o finalizada) se ven en el panel, sin «Aplicar» ni «Rechazar». En la condición no asistida no se piden los posibles errores y no se ve nada (ADR-0040 §13). Los posibles errores descartados no muestran sus sugerencias.
2. **El origen se distingue.** Cada posible error dice de dónde viene: «Regla del validador» o, en un rótulo violeta, «Aprendido de las correcciones» (`learned.*`).
3. **Aplicar es una corrección del editor** (ADR-0036 §5): `POST /sessions/{id}/edits` con el `base_seq` del estado que se ve, la `op`, el ancla y el `after` tal como los propuso el servidor, y `suggestion_id`. Pasa por el mismo camino que cualquier orden: sin actualización optimista, con el estado nuevo de la respuesta (ADR-0037), el 422 que no guarda nada y deshacer (ADR-0034); rehacer la reenvía sin `suggestion_id`.
   - Tras guardarla **queda elegida su nota** (la vecina si la borra, como `selectAfterDelete`), aunque no estuviera elegida al aplicarla, salvo que la persona eligiera otra mientras se guardaba o que haya una orden en espera dada para otra nota (ADR-0038 §7, ADR-0033): esa orden se dio para la nota elegida, y no debe caer en la de la sugerencia.
   - La sugerencia aplicada pasa a «Aplicada» en la lista sin volver a pedirla: el servidor la da por aceptada en la misma transacción.
   - **No espera turno.** Si se está guardando otra orden, no se encola: al guardarse aquella, la sugerencia ya sería antigua. Se dice por qué no se aplicó.
4. **Sugerencias antiguas.** Una sugerencia de una validación anterior al estado que se ve (`at_seq` < `current_seq`) se marca «Antigua: revalida para aplicarla» y no se ofrece aplicarla; tras aplicar una, las demás pasan a serlo, y la barra lo dice («para aplicar otra, revalida la partitura»). La de un estado posterior al que se ve (otra pestaña) dice que hay que recargar.
   - **409 `stale_suggestion`:** el `base_seq` era el del servidor, así que la partitura no cambió y no se recarga. La sugerencia se marca antigua en la vista (por su id, hasta que una revalidación traiga otras), se vuelve a pedir la lista y el panel ofrece «Revalidar». Nunca se reintenta.
   - **409 de `base_seq`:** se recarga como con cualquier orden, y no se ofrece «Volver a aplicar»: sobre el estado recargado la sugerencia es antigua.
5. **Rechazar** es una orden sobre los posibles errores, como descartar (ADR-0035): `POST /sessions/{id}/suggestions/{sid}/reject`, una a la vez con las demás de la lista, sin darla por rechazada antes de la respuesta. Mientras se guarda una corrección (que puede ser la aplicación de esa misma sugerencia) espera, como revalidar. Deja el posible error activo y marcado: descartarlo sigue siendo «Descartar como falso positivo». Un 404 (otra validación cambió los id) vuelve a pedir la lista; un 409 recarga la sesión y dice si está finalizada o si la sugerencia ya se aplicó. Una sugerencia antigua también se puede rechazar (el servidor responde 200).
6. **Las respuestas ya quedan registradas** en el servidor con la versión de la capa (`suggestions.response`, `model_version`, quién y cuándo, ADR-0036 §4), y la «ignorada» se deriva al terminar (ADR-0036 §5). **El contrato no cambia.**
7. **Enmienda 18: lo rechazado no se oculta.** Un `learned.*` cuya única sugerencia se rechazó sigue en la lista, con la sugerencia «Rechazada» y sin acciones sobre ella, y se puede descartar. Ocultarlo, o descartarlo solo al rechazar, haría que rechazar y descartar dijeran lo mismo y escondería un posible error que cuenta en `findings_count`; si el protocolo del estudio necesita otra cosa, lo decide #244.

## Consecuencias

### Positivas
- La capa llega a la persona: cada sugerencia se ve junto al posible error que corrige, con su evidencia, y se aplica con un clic como una corrección más, que se puede deshacer.
- Cada respuesta (aceptada o rechazada) se guarda con la versión de la capa para reentrenar (#256) y para las métricas del estudio (#188), sin cambiar el contrato.

### Negativas / riesgos
- Aplicar una sugerencia deja antiguas las demás hasta revalidar: aplicar varias seguidas exige revalidar entre una y otra. Es lo que pide ADR-0036 §5 (la sugerencia es de la validación de `base_seq`).
- Las sugerencias que el servidor dio por antiguas al aplicarlas se recuerdan solo en la vista abierta: al recargar la página vuelven a ofrecerse, y un nuevo intento responde otra vez `stale_suggestion` sin guardar nada.
- La explicación es el texto del servidor tal cual: si la capa cambia su redacción, la vista la sigue sin cambios.

## Alternativas consideradas

| Alternativa | Motivo del descarte |
|---|---|
| Encolar «Aplicar» como la orden en espera de ADR-0038 | Al guardarse la orden en curso la sugerencia ya es antigua y el servidor respondería `stale_suggestion`. |
| Tras un 409 de `base_seq`, «Volver a aplicar» sin `suggestion_id` | Guardaría el arreglo sin registrar la respuesta a la sugerencia y la daría por aplicada sobre un estado que no se validó. |
| Revalidar sola tras aplicar una sugerencia | Contraria a ADR-0035: la revalidación es explícita, y el estudio mide el tiempo de corrección. |
| Ocultar o descartar el `learned.*` al rechazar su sugerencia | Mezcla rechazar con descartar (#186) y oculta un posible error que sigue contando (enmienda 18). |
| Mostrar la confianza en porcentaje | El issue pide palabras; una cifra sin contexto no ayuda a decidir (ADR-0036 §3). |
