# Vista 03: Tablero Principal / Dashboard de Sesiones

- **Ruta Frontend:** `/dashboard`
- **Acceso:** Protegido (requiere Bearer JWT de `transcriptor` o `investigador`)
- **Modo Impeccable:** `Operate`

---

## 1. Propósito y Audiencia
Es la pantalla principal tras iniciar sesión. Centraliza la gestión de todas las sesiones de transcripción. Permite ver el progreso, retomar una sesión existente, inspeccionar metadatos y lanzar una nueva digitalización.

**Audiencia:** 
- *Transcriptor:* ve y gestiona sus propias sesiones activas y completadas.
- *Investigador:* ve todas las sesiones del sistema de todos los transcriptores.

---

## 2. Contrato de API y Dependencias
- `GET /sessions`:
  - Parámetros de consulta opcionales: `?limit=50&offset=0&status=in_progress|closed`.
  - **Respuesta 200:** Lista de sesiones con `{id, document_id, status, omr_engine, owner_id, created_at, updated_at, findings_count, edits_count}`.
- `GET /auth/me`: Datos del perfil activo para saludo y permisos de rol.

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza   [Buscar partituras...  Ctrl+K]    [● API Online]    admin (investigador) [Salir]|
+--------------------------------------------------------------------------------------------------+
| DASHBOARD DE SESIONES                                                   [ + Nueva Partitura ➔ ]  |
|                                                                                                  |
| [ 12 Sesiones Activas ]   [ 4 Pendientes Revisión ]   [ 28 Completadas ]   [ 94.2% Precisión ]   |
+--------------------------------------------------------------------------------------------------+
| FILTROS Y CONTROLES:                                                                             |
| [Estado: Todos ▾] [Motor: Todos ▾] [Vista: ☵ Tabla | ⊞ Cuadrícula]   [Buscar por obra/id...    ] |
+--------------------------------------------------------------------------------------------------+
| CATÁLOGO DE SESIONES (Vista Tabla de Alta Densidad):                                             |
|                                                                                                  |
| ID        OBRA / COMPOSITOR       ESTADO        MOTOR     HALLAZGOS   EDICIONES  FECHA    ACCIÓN |
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| #8a3f01   Bach · Invención No. 8  [En curso   ] HOMR-GPU  3 alertas   12 edits   14 Oct   [Editar]|
| #7c1e92   Mozart · Sonata K.545   [Finalizada ] HOMR-GPU  0 alertas   4 edits    13 Oct   [Ver]   |
| #4b8a11   Chopin · Preludio No. 4 [Sin revisar] oemer     8 alertas   0 edits    12 Oct   [Editar]|
| #1f9a44   Beethoven · Op. 2 No. 1 [En curso   ] FakeOMR   1 alerta    2 edits    10 Oct   [Editar]|
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| Mostrando 1-4 de 44 sesiones                                                [< Ant] [Sig >]      |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **Header Persistente:**
   - Logotipo con enlace al Dashboard.
   - Disparador de **Command Palette** con chip <kbd>Ctrl+K</kbd>.
   - Perfil de usuario con badge en píldora (`transcriptor` o `investigador`).
   - Botón `Cerrar sesión`.
2. **KPI Strip (Indicadores Rápidos de Productividad):**
   - 4 tarjetas compactas de superficie `#141519` con borde de 1px:
     - Sesiones activas del usuario.
     - Sesiones pendientes de revisión sintáctica.
     - Sesiones finalizadas con éxito.
     - Total de intervenciones o compases procesados.
3. **Barra de Herramientas y Filtrado:**
   - Selector de visualización: **Vista Tabla** (máxima densidad) vs. **Vista Cuadrícula** (tarjetas visuales con la miniatura del escaneo cargada desde `GET /sessions/{id}/image`).
   - Filtros desplegables: por estado (`in_progress`, `closed`), por motor (`homr`, `oemer`, `fake`).
   - Botón de acción principal: Blanco puro `#FFFFFF` con texto negro semibold: `+ Nueva Partitura ➔` (abre `/transcribe`).
4. **Tabla de Sesiones (Vista Predeterminada):**
   - Filas de 38px de altura con hover suave (`rgba(255, 255, 255, 0.04)`).
   - Columnas ordenables (ID, Obra, Estado, Motor, Hallazgos, Ediciones, Fecha).
   - Badges de estado en píldora:
     - `En curso`: azul cobalto `#2563EB`.
     - `Finalizada`: verde esmeralda `#10B981`.
     - `Pendiente`: ámbar `#D97706`.
   - Botón de acción por fila: botón secundario `Abrir Atril ➔` que navega a `/sessions/:id`.
5. **Vista Cuadrícula Alternativa (Grid Cards):**
   - Tarjetas de 260px de ancho con miniatura de la partitura original, título, metadatos y barra de progreso de compases corregidos.

---

## 5. Estados de la Pantalla
- **Cargando:** Esqueletos de carga (*skeletons*) en la tabla sin parpadeo.
- **Vacío (Sin sesiones):** Estado vacío sobrio con icono musical de línea fina y mensaje: *"No tienes sesiones de transcripción activas. Sube una partitura para comenzar."* con botón centrado `Comenzar primera transcripción`.
- **Con datos:** Renderizado rápido de la tabla con paginación limpia.
- **Error:** Alerta de desconexión con botón `Reintentar conexión`.

---

## 6. Atajos de Teclado
- <kbd>Ctrl+K</kbd>: Abre la Command Palette global.
- <kbd>N</kbd>: Atajo rápido para iniciar una nueva partitura (`/transcribe`).
- <kbd>Flecha Abajo / Arriba</kbd>: Navegación entre filas de la tabla.
- <kbd>Enter</kbd>: Abre la sesión seleccionada en la tabla.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Gráficos circulares de dona gigantes o widgets de analítica de marketing innecesarios.
- **Prohibido:** Animaciones lentas de entrada en cascada para cada fila de la tabla; la tabla debe cargar al instante.
- **Prohibido:** Fuentes genéricas sin cifras tabulares; los números deben usar `font-variant-numeric: tabular-nums`.
