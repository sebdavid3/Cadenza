# ADR-0022: Registro de cuentas con activación por un investigador

- **Estado:** Aceptado (enmendado por [ADR-0025](ADR-0025-registro-abierto-sin-aprobacion.md): la cuenta nace activa y desaparece el tope de pendientes; los §4 y §9 ya no rigen)
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

1. **Endpoint público** `POST /auth/register` con `{username, password}`. La contraseña sigue la regla de `POST /users` (al menos 8 caracteres); el nombre, más estricta por ser público: de 3 a 64 caracteres entre minúsculas sin tilde, cifras, punto, guion y guion bajo, empezando por letra o cifra, para que nadie imite visualmente otra cuenta con mayúsculas, espacios o caracteres invisibles. Responde 201 con el perfil (`UserRead`), 409 si el nombre está ocupado, 422 por validación, 429 con `Retry-After` al superar el límite y 503 si hay demasiadas cuentas pendientes (punto 9).
2. **Rol fijo `transcriptor`.** El cuerpo no admite rol; un campo extra se rechaza con 422.
3. **Solo usuario y contraseña**, sin correo ni recuperación, como en ADR-0012.
4. **Cuenta inactiva hasta su activación.** Una cuenta autorregistrada no inicia sesión ni transcribe hasta que un investigador la active con `PATCH /users/{id}`. El inicio de sesión de una cuenta inactiva responde igual que unas credenciales incorrectas (401), como ya hacía `authenticate`; la interfaz lo explica. Esto no oculta qué nombres existen, porque el registro responde 409 a un nombre ocupado: lo que frena el sondeo es el límite por IP.
5. **Marca de origen.** La columna `users.self_registered` (booleano, falso por defecto; migración 0012) distingue las cuentas autorregistradas, y `UserRead` la expone. La exportación del estudio de esfuerzo (`exp_10`, `ml export-effort`) excluye las sesiones cuyo propietario tiene `self_registered = true`; el `DatasetBuilder` del aprendizaje activo todavía no (D55).
6. **Protección contra abuso.**
   - Límite de registros por IP en memoria (`CADENZA_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS` intentos en `CADENZA_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS`), agrupando las IPv6 por su red /64. Comprobar y anotar es una sola operación. Cuentan todos los intentos que llegan a procesarse, también los que acaban en 409, para no permitir sondear nombres sin límite; un cuerpo que no supera el esquema (422) no cuenta porque no toca la base de datos.
   - La IP es la que da uvicorn: detrás del proxy de producción, la real de `X-Forwarded-For` solo si viene del proxy de confianza ([#156](https://github.com/sebdavid3/Cadenza/issues/156)). **Sin ese proxy no conviene abrir el registro**: todas las peticiones llegarían con la misma IP y el límite sería uno solo para todo el servicio.
   - Con el registro abierto, `CADENZA_CORS_ORIGINS` no puede ser `*` (la API no arranca): si lo fuera, cualquier web podría registrar cuentas desde el navegador de sus visitantes y repartir el límite entre todas sus IP.
7. **Ruta pública.** `POST /auth/register` se suma al inicio de sesión y a la comprobación de salud como rutas sin autenticación (ADR-0012 §2).
8. **Desactivable.** `CADENZA_REGISTRATION_ENABLED` (falso por defecto) enciende el registro; apagado, `POST /auth/register` responde 404 antes de leer el cuerpo, sea cual sea. Se enciende en el despliegue público.
9. **Tope de cuentas pendientes.** Con `CADENZA_REGISTRATION_MAX_PENDING` (50 por defecto) cuentas autorregistradas sin activar, el registro responde 503 hasta que un investigador las revise: una avalancha desde muchas IP no llena la lista sin fin.

## Consecuencias

### Positivas
- Cualquiera puede pedir cuenta sin intervención previa del equipo, y nadie consume recursos sin aprobación.
- La gestión de activación reutiliza endpoints existentes; el frontend añade una vista mínima para investigadores ([#155](https://github.com/sebdavid3/Cadenza/issues/155)).
- Las cuentas del público quedan separadas de las del estudio en los datos.

### Negativas / Riesgos
- Un investigador debe revisar y activar cada cuenta; sin notificaciones, la persona no sabe cuándo ocurre.
- El límite por IP vive en memoria y por réplica (como el del login, ADR-0015) y se pierde al reiniciar; las claves sin intentos en la ventana se purgan cuando hay muchas.
- El tope de pendientes también lo puede alcanzar alguien que quiera cerrar el registro a los demás; se reabre en cuanto un investigador activa cuentas.
- No hay estado «rechazada» ni borrado de cuentas: una cuenta autorregistrada que un investigador desactiva vuelve a contar como sin activar, también para el tope (D56). La interfaz las llama «sin activar», no «pendientes».
- Las filas de cuentas inactivas pueden acumularse; un investigador puede dejarlas inactivas (no hay borrado de cuentas).
- El `DatasetBuilder` del plano offline todavía no excluye las sesiones de cuentas autorregistradas; queda como deuda (D55).
- Un cuerpo que no supera la validación del esquema (422) no llega al límite por IP: no toca la base de datos.

## Alternativas consideradas

1. **Registro abierto con la cuenta activa.** Descartado: expone la CPU del servidor a cualquiera.
2. **Código de invitación único en la configuración.** Descartado: acceso inmediato y sin gestión, pero si el código se filtra cualquiera entra, y no deja controlar cada cuenta.
3. **CAPTCHA de terceros.** Descartado: añade un servicio externo y datos de los visitantes a un tercero.
