# Vista 09: Gestión de Usuarios y Roles (Admin)

- **Ruta Frontend:** `/admin/users`
- **Acceso:** Restringido (exclusivo para usuarios con rol `investigador`; un `transcriptor` recibe `403 Forbidden`)
- **Modo Impeccable:** `Operate`

---

## 1. Propósito y Audiencia
Permite a los investigadores supervisores administrar las cuentas del equipo de investigación y de los transcriptores. Incluye dar de alta nuevos usuarios, asignar roles, restablecer contraseñas de forma manual y activar/desactivar cuentas.

**Audiencia:** Investigadores y directores del laboratorio de música/visión artificial.

---

## 2. Contrato de API y Dependencias
- `GET /users`:
  - **Permiso:** Solo rol `investigador`.
  - **Respuesta 200:** Lista de usuarios: `[{"id": "uuid", "username": "string", "role": "transcriptor"|"investigador", "is_active": bool, "created_at": "..."}]`.
- `POST /users`:
  - **Payload:** `{"username": "string", "password": "string", "role": "transcriptor"|"investigador"}`.
  - **Respuesta 201:** Usuario creado con éxito.
  - **Respuesta 409:** Nombre de usuario ya existente.
- `PATCH /users/{user_id}`:
  - **Payload:** `{"is_active": bool, "role": "...", "password": "..."}`.
  - Permite desactivar cuentas o restablecer contraseñas.

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza  PANEL DE ADMINISTRACIÓN: EQUIPO Y USUARIOS                  admin (investigador) |
+--------------------------------------------------------------------------------------------------+
| DIRECTORIO DE USUARIOS DEL SISTEMA                                        [ + Crear Usuario ➔ ]  |
|                                                                                                  |
| [Buscar usuario...                     ]   [Filtro Rol: Todos ▾]   [Estado: Activos ▾]           |
+--------------------------------------------------------------------------------------------------+
| TABLA DE GESTIÓN DE USUARIOS:                                                                    |
|                                                                                                  |
| USUARIO        ROL             ESTADO       FECHA ALTA     SESIONES ACTIVAS   ACCIONES           |
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| admin          [Investigador ] [Activo    ] 01 Oct 2026    12 sesiones        [Editar] [Clave]   |
| sebdavid       [Transcriptor ] [Activo    ] 02 Oct 2026    24 sesiones        [Editar] [Clave]   |
| maria_r        [Transcriptor ] [Activo    ] 05 Oct 2026    8 sesiones         [Editar] [Clave]   |
| carlos_inv     [Investigador ] [Inactivo  ] 08 Oct 2026    0 sesiones         [Activar] [Clave]  |
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| Total: 4 usuarios registrados                                                [Paginación: 1]     |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **Barra Superior y Controles de Búsqueda:**
   - Buscador por nombre de usuario en tiempo real.
   - Filtro por rol (`transcriptor`, `investigador`).
   - Botón primario: Blanco puro `#FFFFFF`: `+ Crear Nuevo Usuario ➔` (abre modal de alta).
2. **Tabla de Usuarios (Alta Densidad):**
   - Altura de fila de 38px con hover suave.
   - Badge de rol:
     - `Investigador`: borde azul cobalto `#2563EB` con fondo sutil.
     - `Transcriptor`: badge neutro plomo `#242731`.
   - Estado de cuenta: punto verde para cuentas activas, punto gris para cuentas suspendidas.
   - Acciones contextuales por fila:
     - `Editar Rol`: cambia entre transcriptor e investigador.
     - `Restablecer Contraseña`: abre modal con campo de nueva clave (mínimo 8 caracteres).
     - `Desactivar / Activar`: toggle rápido con confirmación.
3. **Modal de Creación de Usuario:**
   - Campos: Nombre de usuario (alfanumérico, sin espacios), Contraseña inicial, Selector de Rol.
   - Validación en cliente y feedback inmediato ante conflicto de nombre duplicado (`409 Conflict`).

---

## 5. Estados de la Pantalla
- **Cargando:** Esqueletos de filas de tabla.
- **Acceso Denegado (403):** Si un transcriptor intenta forzar la ruta `/admin/users`, la pantalla muestra una advertencia de acceso restringido con botón para volver al Dashboard.
- **Éxito:** Notificación toast compacta: *"Usuario creado correctamente"*.

---

## 6. Atajos de Teclado
- <kbd>Ctrl+N</kbd>: Abre el modal para crear nuevo usuario.
- <kbd>Esc</kbd>: Cierra los modales activos.
- <kbd>Flechas</kbd>: Navegación por la tabla de usuarios.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Opciones falsas de permisos granulares innecesarios; el modelo de permisos de Cadenza es intencionalmente simple y robusto (ADR-0012: `transcriptor` vs `investigador`).
- **Prohibido:** Permitir que un investigador desactive su propia cuenta si es el único administrador activo.
