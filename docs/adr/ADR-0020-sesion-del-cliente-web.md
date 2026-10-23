# ADR-0020: Sesión del cliente web

- **Estado:** Aceptado
- **Fecha:** 2026-10-22
- **Decisores:** Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0019](ADR-0019-base-del-cliente-web.md)
- **Issue:** [#146](https://github.com/sebdavid3/Cadenza/issues/146)

---

## Contexto

La API emite un JWT de acceso que dura 30 minutos y no tiene refresco
(ADR-0012). `POST /auth/login` recibe un formulario `x-www-form-urlencoded`,
responde 401 ante credenciales inválidas (o cuenta desactivada) y 429 tras cinco
intentos fallidos en 300 s; `GET /auth/me` devuelve el perfil y el rol. El
frontend tenía que decidir dónde guardar el token, cómo recuperar la sesión al
recargar y cómo actuar cuando el token caduca o la API lo rechaza (D47).

## Decisión

1. **Token en `sessionStorage`** (clave `cadenza.token`), además de en memoria:
   - sobrevive a recargar la pestaña, que no debe echar a nadie de una sesión de
     30 minutos;
   - no se comparte entre pestañas ni sobrevive a cerrar la pestaña;
   - si el almacenamiento no está disponible, la sesión vive solo en memoria.
2. **Estado de autenticación en Zustand** (`apps/web/src/auth/store.ts`, ADR-0006):
   `restoring`, `anonymous` o `authenticated`, con el token, el perfil de
   `GET /auth/me` y el motivo de cierre (`expired`) para avisar en el acceso.
3. **Recuperación al arrancar.** Si hay un token guardado y su `exp` no ha
   vencido, se pide `GET /auth/me`. Un 401 cierra la sesión como caducada. Un token
   ya vencido se descarta sin llamar a la API. Las recuperaciones simultáneas
   comparten una sola petición.
4. **Caducidad.** El cliente lee el `exp` del JWT sin verificarlo (la firma la
   comprueba la API) y cierra la sesión al vencer. Cualquier 401 de una petición
   autenticada la cierra también (ADR-0019, `onUnauthorized`). En ambos casos las
   rutas privadas llevan a `/entrar`, que avisa de que la sesión caducó y, tras
   entrar, devuelve a la ruta pedida.
5. **Mensajes del acceso por código de estado:** 401, credenciales inválidas;
   429, demasiados intentos; 422, campos vacíos o no válidos; red, timeout y 5xx,
   los mensajes generales del cliente. El `detail` del backend no se muestra.
6. **«Salir»** borra el token y el estado, sin aviso de caducidad.

## Consecuencias

### Positivas
- Recargar no cierra la sesión; cerrar la pestaña sí.
- La persona sabe por qué vuelve al acceso y regresa adonde estaba.

### Riesgos / costos
- Un token en `sessionStorage` es legible por JavaScript: un XSS podría robarlo
  durante su vida útil. Se mitiga con la vida corta del token y evitando HTML no
  controlado; una cookie `HttpOnly` exigiría cambiar la API y queda fuera de esta
  fase.
- Sin refresco, una sesión de trabajo larga obliga a volver a entrar cada 30
  minutos; lo que haya en curso en la interfaz (por ejemplo, la cola de
  transcripción) se conserva en la pestaña mientras sea la misma persona.

## Alternativas consideradas

1. **Solo en memoria.** Descartado: recargar la página cerraría la sesión.
2. **`localStorage`.** Descartado: la sesión sobreviviría a cerrar el navegador y
   se compartiría entre pestañas sin necesidad.
3. **Cookie `HttpOnly` emitida por la API.** Más segura frente a XSS, pero cambia
   el contrato v1 (y obliga a protegerse de CSRF); fuera de alcance.
