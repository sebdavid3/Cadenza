# ADR-0043: Finalizar y reabrir una sesión desde la vista, con los descartes conservados

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0035, ADR-0036, ADR-0037, ADR-0038 y ADR-0040, CLAUDE.md §9)
- **Enmienda:** [ADR-0014](ADR-0014-ciclo-de-vida-de-la-sesion.md) §2 (finalizar valida como una revalidación, devuelve solo los hallazgos activos y no se repite sobre una sesión ya finalizada)
- **Relacionado:** [ADR-0013](ADR-0013-revalidacion-y-versionado-de-hallazgos.md), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0037](ADR-0037-una-edicion-en-un-solo-viaje.md), [ADR-0038](ADR-0038-redibujar-tras-una-edicion-y-ordenes-en-espera.md), [ADR-0040](ADR-0040-catalogo-de-reglas-y-mensajes-en-lenguaje-musical.md) §13, D38, D65, [#187](https://github.com/sebdavid3/Cadenza/issues/187), [#188](https://github.com/sebdavid3/Cadenza/issues/188)

---

## Contexto

La API ya finaliza y reabre (ADR-0014), pero la web no lo ofrecía. Leído en el código antes de este cambio:

- **D65.** `finalize_session` sustituía los hallazgos del estado final con `replace_findings` sin `dismissed_statuses`: los descartes de la validación vigente volvían a quedar activos y la lista final, la que lee el estudio, los contaba como posibles errores. `revalidate` sí los heredaba (#36, ADR-0035 §13), con una copia de la misma materialización.
- **La condición no asistida.** `transcribe_score` y `revalidate` guardan los hallazgos vacíos en una sesión `unassisted` (D38), pero `finalize_session` ejecutaba las reglas (ADR-0040 §13, ADR-0036 enmienda 13).
- `FinalizeResponse` devolvía todos los hallazgos guardados; `POST /validate`, solo los activos.
- Finalizar una sesión ya finalizada respondía 200 y rehacía la validación final: otros id y, con otra versión de las reglas, otra lista. El contrato ya declaraba un 409 para esa ruta, que nunca se daba.
- La web ya trataba el 409 de una corrección, un deshacer o un descarte en una sesión finalizada (ADR-0030, ADR-0035 §10), y una sesión finalizada ya se veía en solo lectura; no había cómo finalizarla ni reabrirla.
- El estado de la sesión no forma parte de la caché de estados materializados (ADR-0037 §3), que es por `(sesión, seq, última edición)`: finalizar y reabrir no cambian la partitura.

## Decisión

### Backend

1. **Finalizar valida como una revalidación (D65).** `revalidate` y `finalize_session` comparten `store_current_validation` (`cadenza.application.current_validation`): materializa el estado actual, ejecuta las reglas y tras ellas la capa (ADR-0036 §4), hereda los rechazos y los descartes de la validación vigente (`validated_at_seq`, leída antes de sustituirla) mientras su evento no cambie (ADR-0035 §13) y guarda los hallazgos con `replace_findings`. Un descarte restaurado en la validación vigente no vuelve, y uno de una validación anterior es historia.
2. **En `unassisted` no corre nada.** Ni las reglas ni la capa; se guardan los hallazgos vacíos del estado final (ADR-0040 §13).
3. **`FinalizeResponse` trae solo los activos**, como `POST /validate`; los descartados que se conservan se piden con la lista (`include_dismissed`).
4. **Una sesión finalizada no se vuelve a finalizar:** `SessionClosed`, 409, sin tocar sus hallazgos. Su validación final no cambia hasta reabrirla. Reabrir una sesión abierta sigue respondiendo 200: no cambia nada.
5. **Contrato.** Solo cambia la descripción de `POST /sessions/{id}/finalize` en `openapi.json`; ningún esquema, y `types.ts` no cambia. No hay migración: la caché de estados no guarda el estado de la sesión, así que no hay nada que invalidar.

### Web

6. **Quién.** Finaliza y reabre quien transcribió la sesión, como quien la corrige (ADR-0030); un investigador ante una sesión ajena no ve ninguno de los dos botones.
7. **Finalizar pide confirmación.** «Finalizar la corrección», bajo la entradilla de la cabecera, abre debajo una confirmación (`aria-expanded`, foco en «Sí, finalizar», Esc la cierra y devuelve el foco) que dice lo que pasará: se validará la partitura tal como está y la sesión quedará en solo lectura, con el resultado de esa validación; si se te pasó algo, podrás reabrirla. Reabrir no lo pide: no pierde nada.
8. **Nada se da por hecho sin el 200.** Mientras se finaliza, las correcciones esperan (el editor recibe `held`, como al revalidar, ADR-0035 §6) y las órdenes sobre los posibles errores también. Finalizar espera mientras se guarda una corrección, se recarga, hay una orden en espera (ADR-0038) o hay una orden sobre los posibles errores en curso, y lo dice.
9. **El resultado a la vista.** Con el 200 y el `final_seq` del estado que se ve, el detalle pasa a `finalized` sin pedirlo otra vez, se vuelve a pedir la lista (con los descartados que se conservan) y el estado validado se recuerda (ADR-0035 §7). La región `aria-live` del ciclo de vida dice «Sesión finalizada. Validación final: …» con el mismo resumen que una revalidación (cuántos posibles errores, cuántos siguen descartados, y que no señalar nada no garantiza que esté bien). La vista queda en solo lectura: sin barra de corrección, sin descartar ni revalidar, con la lista final y «Reabrir la sesión», que recibe el foco.
10. **El servidor iba por otro estado** (se editó en otra pestaña): se finalizó ese estado y se carga entero (`reload` del editor), y se dice («La sesión iba por un estado posterior al que se veía…»). Finalizar no lleva un `base_seq`: es un cambio del ciclo de vida, no una edición del log (ADR-0011), y la persona puede reabrir si no era lo que quería.
11. **En una sesión no asistida no se habla del validador** (ADR-0040 §13.2): la confirmación y el resultado solo dicen que queda en solo lectura y que se puede reabrir.
12. **Errores.** El 409 dice con su mensaje que la sesión ya estaba finalizada (en otra pestaña o por una petición anterior sin respuesta) y la recarga con su lista, que puede ser de otra validación (si no se puede cargar, lo dice); el 404 y el 403 tienen el suyo. Sin respuesta (red, tiempo agotado, 5xx) se vuelve a pedir el detalle: si la sesión quedó finalizada, se dice y se pide su lista final; si no, se dice que no se sabe si se finalizó y que se puede volver a intentar, que es seguro por el 409. Reabrir sin respuesta hace lo mismo. El `detail` del servidor no se muestra nunca.
13. **Reabrir** pasa el detalle al estado que devuelve (o lo recarga si el servidor va por otro `seq`), dice «Sesión reabierta: puedes seguir corrigiendo.» y lleva el foco a «Finalizar la corrección». La lista sigue siendo la de la validación final, que es la del estado que se ve.
14. **La barra de la corrección no arrastra avisos de otro momento.** Al pasar a finalizada, deja de decir lo de la última orden («Guardado: …», un rechazo, «Sesión recargada», un 409 de otra pestaña o un 422, con su «Volver a aplicar»); al reabrir, deja de decir que la sesión está finalizada. Un 409 de una corrección por estar finalizada se sigue diciendo al pasar a solo lectura.
15. **En el listado**, el estado «Finalizada» va en un rótulo macizo de tinta (`chip--finalized`), distinto del contorno de las sesiones abiertas.
16. **Punto de #188.** Las métricas de esfuerzo se enviarán desde el 200 de finalizar (`useLifecycle.finalize`, marcado con `#188`), con la sesión ya finalizada en `final_seq`. Este ADR no las mide ni las envía.

## Consecuencias

### Positivas
- La lista final de una sesión conserva los descartes de quien la corrigió, y `findings_count` del listado (que cuenta los activos) ya no los suma. Lo comprueban pruebas de la aplicación (descarte vigente conservado, perdido si su evento cambió, restauración respetada, `unassisted` sin reglas ni capa, 409 al repetir) y de la API.
- Una sola implementación de «validar el estado actual»: finalizar y revalidar no pueden volver a separarse.
- Se finaliza y se reabre con el ratón, el dedo o el teclado, con el resultado de la validación final a la vista.

### Negativas / Riesgos
- El 409 de finalizar dos veces se comprueba leyendo el estado antes de validar, sin bloquear la fila: dos finalizaciones simultáneas (un reintento de la web tras agotar el tiempo mientras el servidor aún valida) podrían pasar las dos y validar dos veces el mismo estado. Con una instancia de la API (ADR-0015) y la web esperando a cada respuesta es improbable; cerrarlo exigiría bloquear la sesión (`SELECT … FOR UPDATE`) o un `UPDATE` condicional del estado. La carrera entre una edición y una finalización ya existía.
- Finalizar dos veces da ahora 409. Un cliente que finalizara de nuevo para rehacer la validación final tiene que reabrir antes; la web no lo hace.
- `POST /validate` sigue sin rechazar una sesión finalizada (ADR-0035, riesgos): una pestaña que no lo sepa podría revalidarla y sustituir su validación final por otra del mismo estado, con otros id y los mismos descartes. La vista no ofrece «Revalidar» en una sesión que sabe finalizada.
- Finalizar no lleva `base_seq`: si otra pestaña editó, se finaliza el estado del servidor, y la vista lo dice y lo carga en lugar de impedirlo.
- Cada finalización añade una validación al historial de hallazgos (ADR-0013), como una revalidación; reabrir y volver a finalizar añade otra. Cómo cuentan en las métricas lo decide [#188](https://github.com/sebdavid3/Cadenza/issues/188) con [#244](https://github.com/sebdavid3/Cadenza/issues/244).

## Alternativas consideradas

1. **Copiar en `finalize_session` el bloque de los descartes de `revalidate`.** Descartada: dos copias de la misma materialización y la misma herencia ya se habían separado (D65).
2. **Devolver en `FinalizeResponse` también los descartados, con su estado.** Descartada: quien lea la respuesta sin mirar `status` los contaría como posibles errores, que es lo que D65 quería evitar, y `POST /validate` ya devuelve solo los activos.
3. **Un `base_seq` en finalizar, con 409 si el servidor va por otro estado.** Descartada por ahora: cambia la petición del contrato, y finalizar el estado del servidor, decirlo y dejar reabrir basta para el estudio, que corrige en una pestaña.
4. **Reabrir con confirmación.** Descartada: no pierde nada y se deshace finalizando.
