# ADR-0065: Permiso de uso de los datos al registrarse

- **Estado:** Aceptado (el responsable aprobó el texto del permiso el 2026-11-09)
- **Fecha:** 2026-11-09
- **Decisores:** Responsable del proyecto (que cualquiera pueda crear una cuenta y que quede guardado si dio permiso para usar sus datos, 2026-11-09) y Equipo de Desarrollo
- **Enmienda:** [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md) y [ADR-0025](ADR-0025-registro-abierto-sin-aprobacion.md)
- **Enmendado por:** la enmienda de [#397](https://github.com/sebdavid3/Cadenza/issues/397), que despliega el texto completo en el mismo formulario del registro en lugar de abrirlo en otra pestaña (§4)
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [#378](https://github.com/sebdavid3/Cadenza/issues/378), [#248](https://github.com/sebdavid3/Cadenza/issues/248), [#194](https://github.com/sebdavid3/Cadenza/issues/194)

---

## Contexto

- El registro existe (ADR-0022, ADR-0025): `POST /auth/register` crea un transcriptor activo con usuario y contraseña, sin correo, con un límite por IP. Está detrás de `CADENZA_REGISTRATION_ENABLED` (API) y `VITE_REGISTRATION_ENABLED` (web), apagados por defecto y en producción.
- `users.self_registered` marca estas cuentas, que quedan fuera del estudio y de los datasets de aprendizaje (D55, #191).
- La web no decía en ninguna parte que las imágenes y las correcciones se podrían usar para investigar o para mejorar los modelos.
- El responsable decidió el 2026-11-09 que cualquiera pueda crear una cuenta y que quede guardado si dio permiso para usar sus datos. Usar ese permiso para incluir datos (exportar, tabular o entrenar con ellos) es otro issue, más adelante.

## Decisión

1. **El permiso se guarda en la cuenta: cuándo y qué versión del texto.** `users.data_consent_at` (fecha con zona) y `users.data_consent_version` (texto corto), las dos nulas sin permiso (migración `0017_users_data_consent`). Las cuentas que ya existen quedan sin permiso. No se guarda el historial de cambios: retirarlo borra las dos columnas; cada cambio real (no volver a darlo ni retirar uno que no había) deja una línea `data_consent_changed` en el registro de la API, con la versión que se da o la que se retira.
2. **El texto vive en la web, con una versión compartida.** El texto (`apps/web/src/pages/consent/`) lleva la versión `DATA_CONSENT_VERSION` (la fecha en que se redactó, `2026-11-09`), la misma que la API (`cadenza.application.data_consent`); una prueba comprueba que coinciden, y la página dice la versión con esa misma constante. La descripción del contrato no la cita, para que cambiarla no obligue a regenerarlo. Un permiso es **vigente** si se dio para esa versión: si el texto cambia, cambian las dos, y los permisos dados para el anterior dejan de estar vigentes hasta que se vuelvan a dar.
3. **Registro: un campo opcional, compatible.** `POST /auth/register` acepta `data_consent_version`. Sin él, la cuenta se crea igual, sin permiso (los clientes de antes siguen funcionando). Con la versión vigente, se guarda con la fecha del servidor. Con otra, **409** con `detail: "stale_data_consent"` (un código, como `stale_suggestion`, para que la web lo distinga de un usuario ocupado) y no se crea la cuenta. Con el registro cerrado, el 404 no cambia.
4. **En la web, la casilla es obligatoria para crear la cuenta.** `/registro` enseña un aviso breve (qué se guarda, para qué, con el nombre de usuario, que puede ser un seudónimo, y sin correo), una casilla («Doy mi permiso para que se usen mis datos así.») y un enlace al texto completo en `/uso-de-los-datos`, una página pública que se lee sin cuenta y que desde el registro se abre en otra pestaña, para no perder lo escrito. Sin marcarla, la vista lo dice y no envía nada. El texto completo incluye los derechos de autor de las partituras subidas: solo las que se puedan usar, subirlas no cede sus derechos y Cadenza no publica las imágenes.
5. **Darlo o retirarlo, igual de fácil.** `PUT /auth/data-consent` con `{granted: true, version}` o `{granted: false}` cambia el permiso de la propia cuenta (y de ninguna otra) y devuelve el perfil. Volver a darlo con el mismo texto conserva la fecha de la primera vez. En «Tu cuenta» (`/cuenta`), el mismo aviso y un interruptor que lo da o lo retira con un solo gesto; mientras guarda no se deshabilita (perdería el foco), sino que ignora otro toque. La API lo admite para cualquier cuenta, pero la web solo lo ofrece a las del registro (`self_registered`): a los participantes del estudio, cuyas cuentas crea un investigador, les rige el consentimiento del estudio, y sus datos no dependen de este permiso. El texto completo lo dice.
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
- El texto lo aprobó el responsable el 2026-11-09, sin un contacto para las dudas («habla con el equipo del proyecto»): si se abre el registro al público, conviene añadirlo, y cambiarlo es cambiar la versión.
- Sin historial en la base, saber cuándo se retiró un permiso exige el registro de la API.
- La casilla es obligatoria para crear la cuenta, pero se puede retirar justo después: el issue que use el permiso tiene que tratar igual las cuentas sin permiso vigente.

## Enmienda de #397 (2026-11-10): el texto completo, desplegado en el registro

**El problema.** Desde el registro, el enlace al texto completo se abría en otra pestaña (`target="_blank"`), para que una navegación interna no desmontara el formulario y se perdiera lo escrito. Al responsable no le gustó que el texto aclaratorio abriera otra ventana, y la página `/uso-de-los-datos` le parecía rara (una columna estrecha con la mitad derecha vacía).

**Decisión.** §4 cambia en cómo se lee el texto completo desde el registro; lo demás sigue igual. El responsable eligió entre maquetas:

- En `/registro`, «Leer el texto completo» es un botón (`aria-expanded`, `aria-controls`) que despliega el texto bajo el aviso, antes de la casilla, en un recuadro con su propio desplazamiento y enfocable con el teclado; «Ocultar el texto completo» lo pliega. No abre otra pestaña ni navega, así que lo escrito se conserva. La casilla se sigue describiendo solo con el aviso breve.
- «Tu cuenta» sigue enlazando a la página, que sigue siendo pública. La página pasa a bandas con filetes (el título de cada apartado a la izquierda y el texto a la derecha), según `DESIGN.md`.
- La redacción no cambia, ni su versión: el texto vive en un solo componente (`DataUseText`), que usan la página y el desplegable.

**Alternativas descartadas.** Un diálogo encima del formulario (interrumpe más, y el acceso no usa ventanas modales) y el texto desplegado entero, sin desplazamiento propio (el formulario se alargaba mucho y la casilla quedaba lejos).
