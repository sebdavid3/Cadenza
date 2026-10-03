# ADR-0012: Autenticación e identidad de usuario

- **Estado:** Aceptado
- **Fecha:** 2026-10-03
- **Decisores:** Arquitecto de Software, Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0004](ADR-0004-persistencia-postgresql-jsonb.md), [ADR-0007](ADR-0007-edit-events-inmutables.md), [ADR-0009](ADR-0009-capa-de-aplicacion.md)

---

## Contexto

La API no tiene autenticación. Cualquier cliente puede leer y editar cualquier
sesión si conoce su identificador, y el campo `author` de cada `EditEvent` es un
texto libre que envía el cliente. Esto tiene tres consecuencias:

- **La autoría no es fiable.** El log de ediciones es la evidencia de la tesis
  sobre el esfuerzo de corrección; un autor que el cliente puede escribir a mano
  no sirve para atribuir una sesión a una persona.
- **Las sesiones no son privadas.** Con el listado de sesiones cualquier usuario
  vería el trabajo de los demás.
- **El estudio con participantes no se puede trazar.** Hace falta saber quién
  hizo cada sesión y en qué condición.

Hasta ahora la autenticación estaba fuera del alcance. Se decide incluirla.

## Decisión

Cadenza tiene **autenticación completa**: usuarios con credenciales, inicio de
sesión y sesiones privadas por usuario.

### 1. Usuarios y roles

- Tabla `users` con identificador, nombre de usuario, hash de la contraseña, rol,
  estado (activa o no) y fecha de alta.
- Dos roles: `transcriptor` (corrige sus propias partituras) e `investigador`
  (además crea cuentas y puede leer todas las sesiones para el estudio).
- Las cuentas las crea un investigador. **No hay registro público ni
  recuperación por correo**, de modo que el sistema no necesita datos personales:
  el nombre de usuario de un participante puede ser un código seudónimo.
- Un investigador puede restablecer la contraseña de una cuenta y desactivarla;
  cada usuario puede cambiar la suya. Una cuenta desactivada no inicia sesión.

### 2. Mecanismo

- Inicio de sesión con usuario y contraseña (`POST /auth/login`), que devuelve un
  **token de acceso firmado (JWT) de vida corta**, enviado después como
  `Authorization: Bearer`. No hay tokens de refresco: al caducar, se vuelve a
  iniciar sesión.
- Las contraseñas se guardan con **Argon2id**; nunca en claro ni en los registros.
- La clave de firma y la caducidad del token son configuración
  (`pydantic-settings`).
- Todos los endpoints exigen autenticación, salvo el inicio de sesión y la
  comprobación de salud.

### 3. Propiedad y autoría

- Cada sesión tiene un dueño: `sessions.owner_id` referencia a `users`.
- Un transcriptor solo accede a sus sesiones; pedir una ajena responde igual que
  si no existiera (404). Un investigador puede leer todas, pero solo edita las
  suyas.
- `EditEvent.author`, el descarte de hallazgos y las métricas de esfuerzo los
  **fija el servidor** a partir del usuario autenticado. El cliente deja de
  enviar `author`.

### 4. Ubicación en la arquitectura

- Los casos de uso reciben el **usuario actual** (identificador y rol) como
  parámetro. La regla de propiedad vive en la capa de aplicación, no en los
  *routers*.
- La capa de aplicación declara los puertos `UserRepository`, `PasswordHasher` y
  `TokenService`; sus adaptadores viven en `packages/persistence` y `apps/api`.
- Casos de uso nuevos: `authenticate`, `create_user`, `update_user` y
  `change_password`. Excepciones nuevas:
  `NotAuthenticated` (401) y `Forbidden` (403).
- El dominio no cambia: sigue sin conocer usuarios ni tokens.
- El plano offline no pasa por la API: lee la base de datos con sus propias
  credenciales.

## Consecuencias

### Positivas
- **Autoría fiable** en el log de ediciones y en las métricas de esfuerzo.
- **Sesiones privadas**, requisito para abrir el sistema a más de un usuario.
- El estudio con participantes identifica cada sesión sin tratar datos
  personales.
- La regla de acceso se prueba en la capa de aplicación, sin servidor.

### Riesgos / costos
- Es el cambio de mayor superficie de la fase: toca todos los endpoints, el
  esquema y el contrato de la API, y la interfaz necesita una pantalla de acceso.
- Introduce secretos que gestionar (clave de firma, contraseña del primer
  investigador) y exige HTTPS fuera del equipo de desarrollo.
- Sin tokens de refresco ni revocación, un token robado es válido hasta que
  caduca; se mitiga con una caducidad corta.
- Las sesiones creadas antes de este cambio no tienen dueño; la migración debe
  asignarlas a un usuario inicial.

## Alternativas consideradas

1. **Sin identidad.** Descartado: deja la autoría sin valor como evidencia.
2. **Código seudónimo por participante, sin autenticación.** Descartado: basta
   para el estudio, pero no da sesiones privadas ni autoría verificada.
3. **Proveedor de identidad externo** (inicio de sesión con una cuenta de
   terceros). Descartado: añade una dependencia externa y obliga a tratar datos
   personales.
4. **Sesión de servidor con *cookie*.** Descartado frente al token: exige estado
   en el servidor y protección frente a CSRF, y el flujo con contraseña y token
   es el que FastAPI documenta y genera en OpenAPI.
