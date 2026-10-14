# Vista 02: Autenticación y Acceso

- **Ruta Frontend:** `/login` (y modal `/auth/password`)
- **Acceso:** Público (redirige a `/dashboard` si ya existe token activo en sessionStorage)
- **Modo Impeccable:** `Operate`

---

## 1. Propósito y Audiencia
Permite el acceso seguro al sistema de transcriptores e investigadores mediante autenticación basada en estándares (tokens Bearer JWT conforme a [ADR-0012](../../docs/adr/ADR-0012-autenticacion-e-identidad.md)). 

**Audiencia:** Usuarios registrados (transcriptores e investigadores). No existe formulario de autorregistro público ni recuperación por correo electrónico.

---

## 2. Contrato de API y Dependencias
- `POST /auth/login`:
  - **Payload:** `{"username": "string", "password": "string"}` (form-urlencoded o JSON según contrato).
  - **Respuesta 200:** `{"access_token": "string", "token_type": "bearer", "expires_in": 1800}`.
  - **Respuesta 401:** Credenciales incorrectas.
  - **Respuesta 429:** Bloqueo temporal por exceso de intentos fallidos (`CADENZA_LOGIN_RATE_LIMIT_MAX_ATTEMPTS`).
- `GET /auth/me`: Carga inmediata del perfil tras el login: `{"id": "uuid", "username": "string", "role": "transcriptor" | "investigador"}`.
- `POST /auth/password`: Cambio de contraseña para usuarios autenticados: `{"old_password": "...", "new_password": "..."}`.

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|                                                                                                  |
|                                        [Logo cadenza]                                            |
|                                                                                                  |
|                            +------------------------------------+                                |
|                            | Cadenza Studio Pro                 |                                |
|                            | Inicia sesión para continuar       |                                |
|                            |                                    |                                |
|                            | Usuario                            |                                |
|                            | [ admin                          ] |                                |
|                            |                                    |                                |
|                            | Contraseña                         |                                |
|                            | [ ••••••••••••••••••             ] |                                |
|                            |                                    |                                |
|                            | [ Iniciar Sesión                 ] |                                |
|                            |                                    |                                |
|                            | Las cuentas son creadas por el     |                                |
|                            | administrador del sistema.         |                                |
|                            +------------------------------------+                                |
|                                                                                                  |
|                                  [ ➔ Volver a la portada ]                                       |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Contenido

1. **Tarjeta de Autenticación Centrada:**
   - Superficie `#1A1C22` con borde de `1px solid rgba(255, 255, 255, 0.08)`, radio `8px`, ancho de `380px`.
   - Logotipo `cadenza` en la parte superior en tipografía monoespaciada con punto de estado del servidor (`GET /health`).
2. **Campos de Formulario:**
   - Campo `Usuario`: input de texto con fondo `#141519`, texto `#F3F4F6`, borde `rgba(255, 255, 255, 0.08)` y foco azul cobalto `#2563EB`.
   - Campo `Contraseña`: input tipo password con botón de visibilidad (icono de ojo plano).
3. **Botón Primario de Envío:**
   - Blanco puro `#FFFFFF` con texto `#0C0D0F`, radio `6px`, texto semibold `Iniciar Sesión`. Estado cargando con spinner monoespaciado técnico.
4. **Alerta de Error Accesible:**
   - Mensaje de error en caja roja semántica (`#DC2626` con fondo `rgba(220, 38, 38, 0.12)`) si las credenciales son inválidas o la cuenta está bloqueada temporalmente (429).
5. **Modal de Cambio de Contraseña:**
   - Accesible desde el avatar del usuario una vez autenticado, solicita contraseña actual y nueva contraseña (mínimo 8 caracteres).

---

## 5. Estados de la Pantalla
- **Inicial:** Formulario en blanco con foco automático en el campo `Usuario`.
- **Cargando:** Botón desactivado con indicador `Autenticando...` mientras resuelve `POST /auth/login` y `GET /auth/me`.
- **Error 401:** Mensaje claro: *"Usuario o contraseña incorrectos."*
- **Error 429 (Rate Limit):** Mensaje informativo: *"Demasiados intentos fallidos. Espera unos minutos antes de reintentar."*
- **Sesión Expirada:** Si el token caduca mientras se trabaja, un modal superpuesto solicita la contraseña para renovar el token sin perder el estado del editor.

---

## 6. Atajos de Teclado
- <kbd>Enter</kbd>: Envía el formulario desde cualquier campo.
- <kbd>Tab</kbd> / <kbd>Shift+Tab</kbd>: Navegación secuencial accesible entre inputs y botón.
- <kbd>Esc</kbd>: En el modal de cambio de contraseña, cierra el diálogo.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Botones falsos de *"Iniciar sesión con Google / GitHub / Apple"*; Cadenza es una plataforma soberana on-premise/cloud académica.
- **Prohibido:** Enlaces de *"¿Olvidaste tu contraseña?"* que soliciten correos ficticios (ADR-0012).
- **Prohibido:** Fondos con ilustraciones vectoriales genéricas de oficinas o personas trabajando con laptops. Fondo ónice limpio y sobrio.
