# ADR-0070: Una sola clase de cuenta, sin investigadores

- **Estado:** Aceptado
- **Fecha:** 2026-11-19
- **Decisores:** Responsable del proyecto (decidió el 2026-11-19 que el rol de investigador se sale del alcance y que el estudio con participantes queda fuera) y Equipo de Desarrollo
- **Relacionado:** enmienda [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md), [ADR-0025](ADR-0025-registro-abierto-sin-aprobacion.md), [ADR-0035](ADR-0035-descartar-restaurar-y-revalidar-desde-la-vista.md) y [ADR-0065](ADR-0065-permiso-de-uso-de-los-datos-al-registrarse.md) §5; [#419](https://github.com/sebdavid3/Cadenza/issues/419)

---

## Contexto

ADR-0012 dio a cada cuenta un rol, `transcriptor` o `investigador`. En noviembre de 2026 el rol de investigador solo servía de interruptor de administración: la página `/cuentas` (ver las cuentas y desactivarlas), ver en solo lectura las sesiones de otras personas, y dar de alta las cuentas del estudio (`POST /users`, `scripts/prepare_study_participant.py`). No tenía estadísticas ni vistas de análisis, solo se creaba por línea de comandos (`create-investigator`) y el registro público daba siempre cuentas de transcriptor. Además:

- el rol viajaba en el token de acceso y nadie lo leía: la API vuelve a cargar la cuenta de la base en cada petición y la web solo mira `exp` e `iat`;
- la comprobación de acceso estaba copiada en 18 casos de uso, con 404 para un transcriptor ajeno y 403 para un investigador ajeno;
- un investigador podía revalidar la sesión de otra persona (ADR-0035 §1 lo dejaba anotado como hueco).

El responsable decidió que todo eso se sale del alcance, que el estudio con participantes queda fuera y que no hace falta sustituir la desactivación de cuentas desde la web.

## Decisión

1. **Una sola clase de cuenta.** Desaparecen `Role` y `User.role`. Cada cuenta ve y corrige solo sus sesiones; cualquier otra recibe 404, como si la sesión no existiera. La regla vive en un solo sitio, `cadenza.application.access.require_owner`. Desaparece también `Forbidden`: ningún caso de uso responde 403. Revalidar una sesión ajena deja de estar permitido.
2. **Token sin rol.** El token de acceso lleva `sub`, `exp` e `iat`. Un token emitido antes, con `role`, se sigue aceptando hasta que caduque.
3. **Sin gestión de cuentas.** Se quitan `GET /users`, `POST /users`, `PATCH /users/{id}` y `role` de `UserRead`; el contrato v1 se regenera. Es un cambio incompatible, decidido por el responsable: la web es su único cliente y cambia en el mismo PR. Se quita la CLI `create-investigator`. Una cuenta solo nace del registro público; desactivarla queda en la base, a mano.
4. **Migración 0018.** Quita `users.role`. Bajarla devuelve la columna con `transcriptor` en todas las cuentas: quién era investigador no se recupera. Volver a un código anterior exige antes bajarla o restaurar la copia (`operacion_backend.md`).
5. **Web.** Sin `/cuentas`, sin la etiqueta del rol en la cabecera, sin el dueño de las sesiones en el diario ni en la vista. Con el registro cerrado, la web dice que ahora no se pueden crear cuentas.
6. **Estudio.** Se quitan `scripts/prepare_study_participant.py` y su prueba. `exp_10` y la tabla `partituras` de `ml export-tables` dejan de usar el rol; `self_registered` y el permiso de datos (ADR-0065) se conservan. Sin el filtro del rol, `exp_10` contaría también las sesiones con `test_score_id` de los antiguos investigadores y de la cuenta semilla `default-user` (migración 0005): solo importa si se vuelve a ejecutar. El texto del permiso (`DataUseText`) dejó de nombrar las cuentas del estudio en su versión 2026-11-19 ([#427](https://github.com/sebdavid3/Cadenza/issues/427)): los permisos dados antes dejan de estar vigentes hasta que se vuelvan a dar.

## Consecuencias

- Menos código y una sola regla de acceso, con la misma respuesta (404) para toda sesión ajena.
- Nadie puede ver desde la web las sesiones de otra persona ni las cuentas que existen. Los datos de todas las cuentas se siguen leyendo fuera de la web (`ml export-tables`, el informe de ADR-0069).
- Con el registro cerrado no hay forma de crear una cuenta.
- Las vistas de solo lectura de la web siguen para las sesiones finalizadas y, por defensa, si la sesión no es de quien la ve.

## Alternativas consideradas

1. **Dejar el rol y limpiar alrededor** (comprobación en un solo sitio, rol fuera del token). Descartada: el responsable sacó del alcance a los investigadores y al estudio.
2. **Sustituir `/cuentas` por una CLI para desactivar cuentas.** Descartada por el responsable: no hace falta.
