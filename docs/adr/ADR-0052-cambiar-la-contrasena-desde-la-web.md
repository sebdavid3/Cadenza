# ADR-0052: Cambiar la contraseña desde «Tu cuenta», sin cerrar la sesión abierta

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0012, ADR-0020 y ADR-0022, CLAUDE.md §9)
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0020](ADR-0020-sesion-del-cliente-web.md), [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md), [#190](https://github.com/sebdavid3/Cadenza/issues/190), [#146](https://github.com/sebdavid3/Cadenza/issues/146), [#155](https://github.com/sebdavid3/Cadenza/issues/155)

---

## Contexto

`POST /auth/password` (`ChangePasswordRequest`: `current_password` y `new_password`) ya existe en la API v1, que no cambia. Comprobado contra la API local el 2026-11-01, con contraseñas generadas en cada ejecución:

- **Respuestas.** 200 (`StatusResponse`) al cambiarla; 401 con la contraseña actual equivocada; 422 con una nueva de menos de 8 caracteres o una actual vacía (`detail` con el `loc` del campo). La ruta no tiene límite de intentos: ocho intentos equivocados seguidos responden 401, ninguno 429.
- **El 401 no distingue.** La API responde 401 tanto a la contraseña actual equivocada como a un token que ya no vale (vencido o de una cuenta desactivada).
- **La sesión abierta sigue.** El JWT es sin estado y el cambio no lo invalida: con el token emitido antes del cambio, `GET /auth/me` y `GET /sessions` responden 200 hasta su `exp` (30 minutos por defecto, ADR-0020). La contraseña anterior ya no entra (401) y la nueva sí (200).
- **No hay recuperación por correo** (PRODUCT.md, ADR-0022): la API deja a un investigador restablecer una contraseña (`PATCH /users/{id}` con `password`), pero la web no lo ofrece (#155).

## Decisión

1. **Una vista privada `/cuenta`, «Tu cuenta».** Se llega desde la cabecera de la zona privada: el nombre de la persona en sesión es el enlace (con «Tu cuenta:» para el lector de pantalla), y se marca en su página como las secciones. La vista recuerda con qué cuenta se entró y que no hay recuperación por correo ni desde la web, y tiene un panel «Cambiar la contraseña». No hay menú nuevo ni una entrada «Cuenta» junto a «Cuentas», que a un investigador le confundiría.
2. **Las comprobaciones previas del registro.** La actual no vacía; la nueva de al menos 8 caracteres, contados como la API (`passwordLength`, puntos de código); la repetición igual. Cada error va a su campo, con el foco, y no se envía nada. El formulario lleva `autocomplete` (`current-password`, `new-password`) y el usuario oculto, para el gestor de contraseñas.
3. **El 401 se comprueba antes de decirlo.** La petición va con `notifyUnauthorized: false` (no cierra la sesión). Ante su 401, la vista pide `GET /auth/me` con el cliente de siempre: si responde, el 401 era la contraseña actual («La contraseña actual no es correcta.», en su campo, conservando la nueva); si responde 401, esa petición cierra la sesión como caducada y la ruta privada lleva a entrar. Se descarta leer el `detail` del 401, que es texto del backend y no forma parte del contrato.
4. **Mensajes propios.** 422 en el campo que señala su `loc` (por defecto, la nueva); 429 con el plazo de `Retry-After` si se puede leer, como el registro, aunque hoy la API no lo devuelve en esta ruta (puede venir de un proxy); sin conexión o sin respuesta, que puede que la contraseña llegara a cambiarse.
5. **La sesión abierta no se cierra, y la vista lo dice.** Tras el cambio se vacía el formulario y un aviso con el foco dice que la contraseña cambió, que esta sesión dura hasta la hora en que vence su token (la del almacén de la sesión, ADR-0020), que las abiertas en otras pestañas o navegadores duran hasta que caduquen y que la próxima vez se entra con la nueva. Cerrar la sesión de esta pestaña no protegería de nada: las demás seguirían valiendo, y obligaría a escribir la nueva al momento.

## Consecuencias

- Sin cambios en el contrato ni en el backend.
- Un 401 cuesta una petición más (`GET /auth/me`), solo en el fallo.
- **Deuda para el backend** (fuera de #190, no se toca el contrato): cambiar la contraseña no revoca los tokens emitidos antes, de modo que quien tenga uno robado lo sigue usando hasta su vencimiento; y `/auth/password` no limita los intentos, así que quien tenga un token puede probar contraseñas actuales sin freno. Cerrarlo pediría revocar por versión del usuario (p. ej. `iat` anterior al cambio) y un limitador como el del inicio de sesión. Con tokens de 30 minutos, el riesgo queda acotado.
