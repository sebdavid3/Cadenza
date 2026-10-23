# ADR-0019: Base del cliente web (Fase 8)

- **Estado:** Aceptado
- **Fecha:** 2026-10-22
- **Decisores:** Dirección del proyecto Cadenza
- **Relacionado:** [ADR-0006](ADR-0006-render-editor-osmd-verovio-zustand.md), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0015](ADR-0015-operacion-y-despliegue-del-backend.md), [ADR-0016](ADR-0016-transcripcion-sincrona-vs-asincrona.md)
- **Issue:** [#144](https://github.com/sebdavid3/Cadenza/issues/144)

---

## Contexto

La Fase 8 construye el frontend desde cero en `apps/web`, que tras
[#129](https://github.com/sebdavid3/Cadenza/issues/129) solo conservaba los tipos
generados del contrato (`apps/web/src/types.ts`). La arquitectura fija el stack
(React 18 + TypeScript + Vite; ESLint, Vitest y Playwright) y ADR-0006 el estado
(Zustand para el editor y TanStack Query para el servidor), pero quedaban abiertas
varias decisiones de la base:

- qué versiones concretas usar, ahora que React Router 8 exige React 19 y
  TypeScript 7 no es compatible con `typescript-eslint`;
- cómo llamar a la API: cliente HTTP, timeouts y tratamiento de errores, cuando
  los `detail` del backend mezclan español e inglés y `POST /transcribe` puede
  tardar segundos (ADR-0016);
- cómo acceder a la API en desarrollo sin que sus rutas, que no llevan prefijo,
  choquen con las de la interfaz (frontend-handoff §5.5);
- dónde vive el sistema de diseño.

## Decisión

1. **Versiones.** React 18.3 con React Router 7 (modo biblioteca), Vite 8,
   TypeScript 5.9 en modo estricto (con `noUncheckedIndexedAccess`), ESLint con
   las reglas `strictTypeChecked` de `typescript-eslint`, Prettier, y Vitest con
   Testing Library y jsdom. Se mantiene React 18 porque es lo que fija la
   arquitectura; pasar a React 19 sería un ADR propio.
2. **Cliente HTTP propio sobre `fetch`** (`apps/web/src/api/client.ts`), sin axios:
   - URL base configurable con `VITE_API_BASE_URL`, `/api` por defecto;
   - `Authorization: Bearer` a partir de un proveedor de token, salvo en las rutas
     públicas;
   - timeout por petición con `AbortController`: 15 s por defecto y 30 s para
     `POST /transcribe` (frontend-handoff §5.7);
   - errores tipados (`ApiError`) según el código de estado, la red, el timeout o
     la cancelación, cada uno con un mensaje propio en español. El `detail` del
     backend se conserva para depurar y nunca se muestra;
   - un 401 de una petición que llevaba token avisa a la aplicación
     (`onUnauthorized`) para cerrar la sesión; el 401 de un inicio de sesión
     fallido no, porque no lleva token.
3. **Acceso a la API en desarrollo mediante el proxy de Vite** bajo el prefijo
   `/api`, que se quita al reenviar (`CADENZA_API_PROXY_TARGET`, por defecto
   `http://127.0.0.1:8000`). Ninguna ruta de la interfaz empieza por `/api`. En un
   despliegue, o un proxy inverso con el mismo prefijo, o `VITE_API_BASE_URL` con
   la URL de la API y su origen en `CADENZA_CORS_ORIGINS` (ADR-0015).
4. **Contrato.** `src/types.ts` se importa tal cual y no se edita a mano: lo
   regenera `scripts/generate_openapi_and_types.py` y lo vigila pytest. ESLint y
   Prettier lo excluyen.
5. **Sistema de diseño con Impeccable.** `PRODUCT.md` (raíz) recoge el producto;
   el contrato de dirección de cada superficie vive en `.impeccable/surfaces/`;
   `DESIGN.md` y `.impeccable/design.json` se escriben a partir de la primera
   superficie construida, la landing ([#145](https://github.com/sebdavid3/Cadenza/issues/145)).
   Los tokens son propiedades CSS (`src/styles/tokens.css`) y las tipografías se
   sirven desde el proyecto con paquetes `@fontsource` (subconjunto latino), sin
   hojas de estilo de terceros.
6. **CI.** Un job `frontend` en Node 24 ejecuta `npm ci`, `npm run lint`,
   `npm run format:check`, `npm run test` y `npm run build`.

## Consecuencias

### Positivas
- El cliente no depende de bibliotecas externas y sus reglas (timeout, token,
  errores) se prueban en aislamiento.
- Ninguna vista muestra un `detail` en bruto ni un mensaje en inglés.
- El proxy reproduce en desarrollo un despliegue con el mismo origen y no depende
  de la configuración de CORS.

### Riesgos / costos
- React 18 dejará de recibir novedades; las dependencias que exijan React 19
  (React Router 8, por ejemplo) obligarán a revisar esta decisión.
- Con el proxy, un cambio de puerto o de host del backend se configura en
  `CADENZA_API_PROXY_TARGET`, no en el código.

## Alternativas consideradas

1. **React 19 con React Router 8.** Descartado por ahora: contradice la tabla de
   stack de la arquitectura sin aportar nada que esta tanda necesite.
2. **axios.** Descartado: `fetch` con `AbortController` cubre el timeout, la
   cancelación y los cuerpos `multipart/form-data` y `x-www-form-urlencoded`.
3. **CORS directo en desarrollo** (`CADENZA_CORS_ORIGINS=*`). Funciona, pero sigue
   disponible con `VITE_API_BASE_URL`; el proxy evita depender de esa
   configuración.
4. **TypeScript 7.** Descartado mientras `typescript-eslint` no lo admita.
