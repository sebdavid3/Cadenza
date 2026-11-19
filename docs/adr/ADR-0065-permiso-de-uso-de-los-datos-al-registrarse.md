# ADR-0065: Permiso de uso de los datos al registrarse

- **Estado:** Aceptado (el responsable aprobó el texto del permiso el 2026-11-09. Enmendado por [ADR-0070](ADR-0070-una-sola-clase-de-cuenta.md): sin investigadores; el §5 sigue rigiendo las cuentas que ya existían. El texto pasó a la versión 2026-11-19 sin el párrafo del estudio ([#427](https://github.com/sebdavid3/Cadenza/issues/427)): los permisos de 2026-11-09 dejaron de estar vigentes. Enmendado por [#422](https://github.com/sebdavid3/Cadenza/issues/422): los datos de las cuentas con el permiso vigente entran por defecto, §7)
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
2. **El texto vive en la web, con una versión compartida.** El texto (`apps/web/src/pages/consent/`) lleva la versión `DATA_CONSENT_VERSION` (la fecha en que se redactó: `2026-11-09` y, desde [#427](https://github.com/sebdavid3/Cadenza/issues/427), `2026-11-19`), la misma que la API (`cadenza.application.data_consent`); una prueba comprueba que coinciden, y la página dice la versión con esa misma constante. La descripción del contrato no la cita, para que cambiarla no obligue a regenerarlo. Un permiso es **vigente** si se dio para esa versión: si el texto cambia, cambian las dos, y los permisos dados para el anterior dejan de estar vigentes hasta que se vuelvan a dar.
3. **Registro: un campo opcional, compatible.** `POST /auth/register` acepta `data_consent_version`. Sin él, la cuenta se crea igual, sin permiso (los clientes de antes siguen funcionando). Con la versión vigente, se guarda con la fecha del servidor. Con otra, **409** con `detail: "stale_data_consent"` (un código, como `stale_suggestion`, para que la web lo distinga de un usuario ocupado) y no se crea la cuenta. Con el registro cerrado, el 404 no cambia.
4. **En la web, la casilla es obligatoria para crear la cuenta.** `/registro` enseña un aviso breve (qué se guarda, para qué, con el nombre de usuario, que puede ser un seudónimo, y sin correo), una casilla («Doy mi permiso para que se usen mis datos así.») y un enlace al texto completo en `/uso-de-los-datos`, una página pública que se lee sin cuenta y que desde el registro se abre en otra pestaña, para no perder lo escrito. Sin marcarla, la vista lo dice y no envía nada. El texto completo incluye los derechos de autor de las partituras subidas: solo las que se puedan usar, subirlas no cede sus derechos y Cadenza no publica las imágenes.
5. **Darlo o retirarlo, igual de fácil.** `PUT /auth/data-consent` con `{granted: true, version}` o `{granted: false}` cambia el permiso de la propia cuenta (y de ninguna otra) y devuelve el perfil. Volver a darlo con el mismo texto conserva la fecha de la primera vez. En «Tu cuenta» (`/cuenta`), el mismo aviso y un interruptor que lo da o lo retira con un solo gesto; mientras guarda no se deshabilita (perdería el foco), sino que ignora otro toque. La API lo admite para cualquier cuenta, pero la web solo lo ofrece a las del registro (`self_registered`): a los participantes del estudio, cuyas cuentas creaba un investigador (los retiró ADR-0070), les rige el consentimiento del estudio, y sus datos no dependen de este permiso. El texto completo lo dice.
6. **El perfil lo dice.** `UserRead` lleva `data_consent` (vigente), `data_consent_at` y `data_consent_version`.
7. **Solo se guarda.** Nada lee el permiso para decidir qué datos se usan: `ml build-dataset`, `ml suggestions build-dataset` y `exp_10` dan lo mismo con él que sin él, y las cuentas del registro siguen fuera aunque lo hayan dado (pruebas en `packages/learning/tests`). Cuando otro issue lo use, decidirá qué hacer con las cuentas sin permiso vigente y con lo ya usado antes de retirarlo. *(Ya no vale: lo leen las tablas y el corpus de sugerencias desde la enmienda de #400 y, por defecto, todos los comandos desde la de #422.)*
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

## Enmienda de #400 (2026-11-12): las tablas y el corpus de sugerencias leen el permiso

**El problema.** `ml export-tables` ([#400](https://github.com/sebdavid3/Cadenza/issues/400)) y `ml suggestions build-dataset` comparten `session_records`, que con `--include-self-registered` metía todas las cuentas del registro, tuvieran o no el permiso. `ml export-staves` (ADR-0067) ya exigía el permiso vigente por decisión del responsable del 2026-11-11, así que las dos exportaciones no daban las mismas sesiones.

**Decisión.** §7 deja de valer para esos dos comandos. Por defecto las cuentas del registro siguen fuera; con `--include-self-registered` entran solo las que tienen el permiso de la versión vigente del texto (`has_current_data_consent`), y las demás quedan fuera con el motivo «cuenta del registro sin el permiso de uso de los datos vigente». La columna `permiso_datos` de `partituras.csv` dice si el permiso es vigente, no solo si se dio alguna vez. `ml build-dataset` (D55) y `exp_10` no cambian.

## Enmienda de #430 (2026-11-19): el permiso se pide al entrar

**El problema.** #427 cambió el texto y subió la versión a 2026-11-19, así que los permisos dados para la 2026-11-09 dejaron de estar vigentes (§2). Solo «Tu cuenta» lo decía, y casi nadie la abre: sin volver a darlo, los datos de esas cuentas quedan fuera de las exportaciones, del entrenamiento y de las cifras de la Fase 12 (#422, #423).

**Decisión** (del responsable, 2026-11-19). §5 se amplía. A una cuenta del registro que dio el permiso para un texto anterior, la zona privada le pide volver a darlo nada más entrar, en una banda bajo la cabecera (`ConsentPrompt`). La banda dice que el texto cambió, enseña el mismo aviso breve que el registro y «Tu cuenta», y enlaza al texto completo. Ofrece «Doy mi permiso», que envía `PUT /auth/data-consent` con la versión vigente como el interruptor, y «Ahora no».

- «Ahora no» vale para esa entrada, también al recargar, porque se guarda en `sessionStorage` con la cuenta, la versión y el vencimiento de la sesión. En la siguiente entrada se vuelve a pedir.
- Nada obliga a darlo: sin él, Cadenza se usa igual, como promete el texto.
- No sale en la vista de una sesión, que necesita todo su alto (#363), ni en «Tu cuenta», que tiene su interruptor. Tampoco sale a quien lo tiene vigente ni a las cuentas que no son del registro.
- A quien lo retiró no se le insiste. Retirarlo borra la versión (§5), así que no queda un permiso anterior que renovar, y puede volver a darlo en «Tu cuenta». Lo señaló la revisión independiente: desde #378 la casilla del registro es obligatoria, así que una cuenta del registro sin versión es casi siempre una que lo retiró.
- Accesibilidad: el agradecimiento va en una región viva que existe desde el principio, y el foco pasa a «Cerrar». Al cerrar o con «Ahora no», el foco vuelve al `h1` de la página. El rótulo de la banda no es un encabezado, porque va antes del `h1`.

No cambian el texto, la versión, la API ni el contrato.

## Enmienda de #422 (2026-11-19): los datos con el permiso vigente entran por defecto

**El problema.** Desde el 2026-11-10 el permiso es obligatorio para registrarse y cubre investigar y entrenar los modelos, y desde ADR-0070 toda cuenta nueva sale del registro. Pero solo `ml export-pairs` (ADR-0071) dejaba entrar por defecto las cuentas del registro con el permiso vigente. `ml export-tables`, `ml export-staves` y `ml suggestions build-dataset` solo las metían con `--include-self-registered`, y `ml build-dataset` las dejaba fuera o, con esa opción, las metía todas, tuvieran el permiso o no. Casi todos los datos nuevos se quedaban fuera.

**Decisión** (del responsable, 2026-11-19, [#422](https://github.com/sebdavid3/Cadenza/issues/422)). §7 deja de valer, y la enmienda de #400 en lo que tenía de opción.

- **Una sola regla para todos los comandos de `ml` que leen la base** (`cadenza.learning.consent.filter_by_consent`): `export-pairs`, `export-tables` (también con `--recortes`), `export-staves`, `build-dataset` (`RepositoryDatasetReader`, también dentro de `ml run`) y `suggestions build-dataset` (`session_records`).
  - Las cuentas que no vienen del registro (las del equipo y las del estudio, anteriores a ADR-0070) entran: no se les pidió este permiso.
  - Las del registro entran por defecto si tienen el permiso del texto vigente (`has_current_data_consent`). Con `--exclude-self-registered`, ninguna.
  - Las del registro sin el permiso vigente (nunca lo dieron, lo retiraron o lo dieron para otro texto) quedan siempre fuera, también con opciones, como promete el texto.
  - Una sesión cuya cuenta no está queda fuera, con el motivo «sin la cuenta de su dueño» en las exportaciones (`build-dataset` no lista lo que deja fuera): no se sabe si tiene el permiso. Antes entraba en las tablas, en los recortes y, con la opción, en el dataset.
- **Lo que deja fuera el permiso solo se cuenta.** Ni su identificador ni su motivo van a `left_out`. `run_info.json`, y `dataset.json` en `build-dataset`, llevan un bloque `consent` con la versión del texto, `sessions_without_current_consent` y `sessions_excluded_by_option`. `ml suggestions build-dataset`, que no escribe `run_info.json`, imprime los dos números. Se cuentan entre las sesiones que el comando considera: las finalizadas o, con `--include-unfinished`, todas. En `filters`, `exclude_self_registered` sustituye a `include_self_registered`.
- **`--include-self-registered` se retira.** Lo que pedía es ahora lo de por defecto. El comando la sigue reconociendo, sin enseñarla en la ayuda, solo para fallar sin escribir nada (código 2) con un mensaje que lo explica y nombra `--exclude-self-registered` (`ml/consent_cli.py`).
- **Lo decide el permiso, no si la cuenta está activa.** Una cuenta desactivada (`active` falso) con el permiso vigente sigue entrando: desactivar corta el acceso, no retira el permiso (decisión del responsable del 2026-11-19, en la revisión de #442).
- `ml build-dataset --owner-id` con una cuenta que no entra (no existe, no tiene el permiso vigente o la deja fuera la opción) sigue siendo un error, no un dataset vacío.

**Alternativas descartadas.**

- **Dejar `--include-self-registered` sin efecto, con un aviso.** Una receta vieja seguiría funcionando, pero en `build-dataset` la opción metía también las cuentas sin el permiso: daría en silencio un dataset distinto del que esperaba quien la escribió, y quedaría para siempre una opción que no hace nada. Retirarla cuesta quitarla de la receta una vez.
- **Dejar las sesiones sin permiso en `left_out`, con su identificador**, como hacían `export-tables` y `export-staves` desde #400. Son datos de quien no dio permiso para usarlos; `export-pairs` ya solo las contaba.

**Consecuencias.**

- Con la misma base entran más sesiones: las exportaciones y los datasets de antes no se comparan uno a uno con los de ahora, y la obra de una sesión puede cambiar de lado (ADR-0036, enmienda de #437).
- `partituras.csv` lleva, por defecto, el nombre de usuario (`participante`) de las cuentas del registro que entran. Lo cubre el permiso (§4: los datos se usan con el nombre de usuario, que puede ser un seudónimo), y la carpeta se trata como los datos de personas que es (ADR-0068).
- Quien retira el permiso deja de entrar desde ese momento. Una exportación ya escrita es una foto fija: se borra y se vuelve a hacer (ADR-0067 §4, ADR-0071).
- Un permiso dado para el texto anterior no cuenta hasta que se vuelve a dar (enmienda de #430).
- No cambian el texto del permiso, su versión, la API ni el contrato.
