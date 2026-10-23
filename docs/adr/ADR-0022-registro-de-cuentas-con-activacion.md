# ADR-0022: Registro de cuentas con activación por un investigador

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Dirección del proyecto Cadenza (decisión aprobada por el responsable el 2026-10-23), Equipo de Desarrollo
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md) (enmienda su §1), [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md)

---

## Contexto

ADR-0012 §1 establece que las cuentas las crea un investigador y que no hay registro público ni recuperación por correo. Cadenza se va a desplegar como servicio público ([#156](https://github.com/sebdavid3/Cadenza/issues/156), [#157](https://github.com/sebdavid3/Cadenza/issues/157)) y se quiere que cualquiera pueda pedir una cuenta sin escribir al equipo ([#154](https://github.com/sebdavid3/Cadenza/issues/154)).

Restricciones:

- Cada transcripción consume CPU (o GPU) del servidor del responsable: un registro totalmente abierto invita al abuso.
- El estudio de la tesis usa cuentas seudónimas creadas por investigadores (`sessions.condition` vale «assisted» por defecto). Las cuentas creadas por el público no deben mezclarse con las del estudio.
- No se quieren datos personales (ADR-0012): ni correo ni recuperación.
- La API ya permite a un investigador activar o desactivar una cuenta (`PATCH /users/{id}` con `active`) y una cuenta inactiva no inicia sesión.
- Sin CAPTCHA ni otros servicios de terceros.

## Decisión

Se **enmienda ADR-0012 §1**: además de las cuentas que crea un investigador, cualquiera puede registrarse, pero la cuenta nace **inactiva** hasta que un investigador la active.

1. **Endpoint público** `POST /auth/register` con `{username, password}` (las mismas reglas que `POST /users`: nombre de 1 a 64 caracteres y contraseña de al menos 8). Responde 201 con el perfil (`UserRead`), 409 si el nombre está ocupado, 422 por validación y 429 con `Retry-After` al superar el límite.
2. **Rol fijo `transcriptor`.** El cuerpo no admite rol; un campo extra se rechaza con 422.
3. **Solo usuario y contraseña**, sin correo ni recuperación, como en ADR-0012.
4. **Cuenta inactiva hasta su activación.** Una cuenta autorregistrada no inicia sesión ni transcribe hasta que un investigador la active con `PATCH /users/{id}`. El inicio de sesión de una cuenta inactiva responde igual que unas credenciales incorrectas (401), para no revelar qué nombres existen; la interfaz lo explica.
5. **Marca de origen.** La columna `users.self_registered` (booleano, falso por defecto; migración 0012) distingue las cuentas autorregistradas, y `UserRead` la expone. El análisis del estudio excluye las sesiones cuyo propietario tiene `self_registered = true`.
6. **Protección contra abuso.** Límite de registros por IP en memoria (`CADENZA_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS` intentos en `CADENZA_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS`), con la IP que da uvicorn; detrás del proxy de producción, uvicorn toma la IP real de `X-Forwarded-For` solo si viene del proxy de confianza ([#156](https://github.com/sebdavid3/Cadenza/issues/156)). Cuentan todos los intentos, también los fallidos, para no permitir sondear nombres sin límite.
7. **Ruta pública.** `POST /auth/register` se suma al inicio de sesión y a la comprobación de salud como rutas sin autenticación (ADR-0012 §2).
8. **Desactivable.** `CADENZA_REGISTRATION_ENABLED` (falso por defecto) enciende el registro; apagado, `POST /auth/register` responde 404, como una ruta que no existe. Se enciende en el despliegue público.

## Consecuencias

### Positivas
- Cualquiera puede pedir cuenta sin intervención previa del equipo, y nadie consume recursos sin aprobación.
- La gestión de activación reutiliza endpoints existentes; el frontend añade una vista mínima para investigadores ([#155](https://github.com/sebdavid3/Cadenza/issues/155)).
- Las cuentas del público quedan separadas de las del estudio en los datos.

### Negativas / Riesgos
- Un investigador debe revisar y activar cada cuenta; sin notificaciones, la persona no sabe cuándo ocurre.
- El límite por IP vive en memoria y por réplica (como el del login, ADR-0015) y se pierde al reiniciar.
- Las filas de cuentas inactivas pueden acumularse; un investigador puede dejarlas inactivas (no hay borrado de cuentas).
- El plano offline (`DatasetBuilder`) todavía no excluye las sesiones de cuentas autorregistradas; queda como deuda (D55).
- Un cuerpo que no supera la validación del esquema (422) no llega al límite por IP: no toca la base de datos.

## Alternativas consideradas

1. **Registro abierto con la cuenta activa.** Descartado: expone la CPU del servidor a cualquiera.
2. **Código de invitación único en la configuración.** Descartado: acceso inmediato y sin gestión, pero si el código se filtra cualquiera entra, y no deja controlar cada cuenta.
3. **CAPTCHA de terceros.** Descartado: añade un servicio externo y datos de los visitantes a un tercero.
