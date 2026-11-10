# ADR-0064: Permiso de uso de los datos al registrarse

- **Estado:** Aceptado (el texto del permiso es una propuesta que aprueba el responsable antes de fusionar)
- **Fecha:** 2026-11-09
- **Decisores:** Responsable del proyecto (que cualquiera pueda crear una cuenta y que quede guardado si dio permiso para usar sus datos, 2026-11-09) y Equipo de Desarrollo
- **Enmienda:** [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md) y [ADR-0025](ADR-0025-registro-abierto-sin-aprobacion.md)
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [#378](https://github.com/sebdavid3/Cadenza/issues/378), [#248](https://github.com/sebdavid3/Cadenza/issues/248), [#194](https://github.com/sebdavid3/Cadenza/issues/194)

---

## Contexto

- El registro existe (ADR-0022, ADR-0025): `POST /auth/register` crea un transcriptor activo con usuario y contraseña, sin correo, con un límite por IP. Está detrás de `CADENZA_REGISTRATION_ENABLED` (API) y `VITE_REGISTRATION_ENABLED` (web), apagados por defecto y en producción.
- `users.self_registered` marca estas cuentas, que quedan fuera del estudio y de los datasets de aprendizaje (D55, #191).
- La web no decía en ninguna parte que las imágenes y las correcciones se podrían usar para investigar o para mejorar los modelos.
- El responsable decidió el 2026-11-09 que cualquiera pueda crear una cuenta y que quede guardado si dio permiso para usar sus datos. Usar ese permiso para incluir datos (exportar, tabular o entrenar con ellos) es otro issue, más adelante.

## Decisión

1. **El permiso se guarda en la cuenta: cuándo y qué versión del texto.** `users.data_consent_at` (fecha con zona) y `users.data_consent_version` (texto corto), las dos nulas sin permiso (migración `0017_users_data_consent`). Las cuentas que ya existen quedan sin permiso. No se guarda el historial de cambios: retirarlo borra las dos columnas; cada cambio deja una línea `data_consent_changed` en el registro de la API.
2. **El texto vive en la web, con una versión compartida.** El texto (`apps/web/src/pages/consent/`) lleva la versión `DATA_CONSENT_VERSION` (la fecha en que se redactó, `2026-11-09`), la misma que la API (`cadenza.application.data_consent`); una prueba comprueba que coinciden. Un permiso es **vigente** si se dio para esa versión: si el texto cambia, cambian las dos, y los permisos dados para el anterior dejan de estar vigentes hasta que se vuelvan a dar.
3. **Registro: un campo opcional, compatible.** `POST /auth/register` acepta `data_consent_version`. Sin él, la cuenta se crea igual, sin permiso (los clientes de antes siguen funcionando). Con la versión vigente, se guarda con la fecha del servidor. Con otra, **409** con `detail: "stale_data_consent"` (un código, como `stale_suggestion`, para que la web lo distinga de un usuario ocupado) y no se crea la cuenta. Con el registro cerrado, el 404 no cambia.
4. **En la web, la casilla es obligatoria para crear la cuenta.** `/registro` enseña un aviso breve (qué se guarda, para qué y con seudónimo), una casilla («Doy mi permiso para que se usen mis datos así.») y un enlace al texto completo en `/uso-de-los-datos`, una página pública que se lee sin cuenta. Sin marcarla, la vista lo dice y no envía nada.
5. **Darlo o retirarlo, igual de fácil.** `PUT /auth/data-consent` con `{granted: true, version}` o `{granted: false}` cambia el permiso de la propia cuenta (y de ninguna otra) y devuelve el perfil. Volver a darlo con el mismo texto conserva la fecha de la primera vez. En «Tu cuenta» (`/cuenta`), el mismo aviso y un interruptor que lo da o lo retira con un solo gesto. Vale para cualquier cuenta, también las que crea un investigador.
6. **El perfil lo dice.** `UserRead` lleva `data_consent` (vigente), `data_consent_at` y `data_consent_version`.
7. **Solo se guarda.** Nada lee el permiso para decidir qué datos se usan: `ml build-dataset`, `ml suggestions build-dataset` y `exp_10` dan lo mismo con él que sin él, y las cuentas del registro siguen fuera aunque lo hayan dado (pruebas en `packages/learning/tests`). Cuando otro issue lo use, decidirá qué hacer con las cuentas sin permiso vigente y con lo ya usado antes de retirarlo.
8. **Producción no cambia.** El registro sigue apagado; `operacion_backend.md` §2.2 dice cómo encenderlo.

## Alternativas descartadas

- **Exigir el permiso en la API.** Rompería a los clientes que se registran sin el campo y mezclaría el contrato con una regla de la interfaz; la web lo exige y la API lo guarda.
- **Una tabla de permisos con su historial.** Más fiel a una auditoría, pero el responsable pidió guardar cuándo y qué versión; el historial queda en el registro de la API y, si el issue que use el permiso lo necesita, se añade entonces.
- **Que la API sirva el texto.** Obligaría a duplicar en la API un texto de interfaz; basta con que compartan la versión.

## Consecuencias

### Positivas
- Queda constancia, por cuenta, de quién dio permiso y para qué texto, antes de abrir el registro.
- Cambiar el texto obliga a cambiar la versión, y los permisos antiguos dejan de contar sin tocar la base.

### Negativas / Riesgos
- El texto es una propuesta: hasta que el responsable lo apruebe, no debe encenderse el registro.
- Sin historial en la base, saber cuándo se retiró un permiso exige el registro de la API.
- La casilla es obligatoria para crear la cuenta, pero se puede retirar justo después: el issue que use el permiso tiene que tratar igual las cuentas sin permiso vigente.
