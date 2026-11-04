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

1. **Token en `sessionStorage`** (claves `cadenza.token` y `cadenza.token.caduca`),
   además de en memoria:
   - sobrevive a recargar la pestaña, que no debe echar a nadie de una sesión de
     30 minutos;
   - no sobrevive a cerrar la pestaña ni se comparte con otras pestañas abiertas
     por separado (el «duplicar pestaña» del navegador sí copia `sessionStorage`);
   - si el almacenamiento no está disponible, la sesión vive solo en memoria.
2. **Estado de autenticación en Zustand** (`apps/web/src/auth/store.ts`, ADR-0006):
   `restoring`, `unreachable`, `anonymous` o `authenticated`, con el token, su
   caducidad local, el perfil de `GET /auth/me` y el motivo del último cierre
   (`expired` o `signed-out`).
3. **Recuperación al arrancar.** Si hay un token guardado y no ha caducado, se pide
   `GET /auth/me`:
   - con 200 se recupera la sesión; con 401 se cierra como caducada;
   - sin conexión, timeout o 5xx se conserva el token y la ruta privada ofrece
     «Reintentar» (`unreachable`), en vez de echar a la persona;
   - un token ya caducado se descarta sin llamar a la API;
   - el resultado solo se aplica si la sesión sigue en comprobación: si mientras
     tanto la persona entró o salió, no se pisa; las recuperaciones simultáneas
     comparten una petición, y mientras se comprueba no se puede enviar el acceso.
4. **Caducidad.** El cliente lee `exp` e `iat` del JWT sin verificarlo (la firma
   la comprueba la API) y cuenta la vida del token (`exp - iat`) desde que lo
   recibe, en su propio reloj: un reloj del equipo desajustado no acorta ni alarga
   la sesión. Al vencer la cierra; el temporizador se reprograma por tramos por
   debajo del límite de `setTimeout`. Un 401 de una petición autenticada la cierra
   también (ADR-0019, `onUnauthorized`), pero solo si el token rechazado es el
   vigente: un 401 tardío de una sesión anterior no cierra la nueva. En ambos casos
   las rutas privadas llevan a `/entrar`, que avisa de que la sesión caducó y, tras
   entrar, devuelve a la ruta pedida (solo rutas internas).
5. **Mensajes del acceso por código de estado:** 401, credenciales inválidas;
   429, demasiados intentos; 422, campos vacíos o no válidos; red, timeout y 5xx,
   los mensajes generales del cliente. El `detail` del backend no se muestra.
6. **«Salir»** borra el token y el estado, sin aviso de caducidad y sin recordar
   la ruta: la siguiente persona en la pestaña empieza desde la vista por defecto.

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
  minutos. Lo que conserve cada vista mientras tanto lo decide la vista (la de
  transcripción, [#147](https://github.com/sebdavid3/Cadenza/issues/147)).

## Alternativas consideradas

1. **Solo en memoria.** Descartado: recargar la página cerraría la sesión.
2. **`localStorage`.** Descartado: la sesión sobreviviría a cerrar el navegador y
   se compartiría entre pestañas sin necesidad.
3. **Cookie `HttpOnly` emitida por la API.** Más segura frente a XSS, pero cambia
   el contrato v1 (y obliga a protegerse de CSRF); fuera de alcance.
