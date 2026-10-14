# Vista 01: Home / Landing Institucional

- **Ruta Frontend:** `/`
- **Acceso:** Público (sin autenticación requerida)
- **Modo Impeccable:** `Persuade` / `Read`

---

## 1. Propósito y Audiencia
La **Home Institucional** es la cara pública del proyecto Cadenza. Presenta la fundamentación científica de la tesis: la digitalización asistida de partituras mediante la combinación sinérgica de reconocimiento óptico de música (OMR), validación de reglas de teoría musical y corrección humana de alta precisión (*Human-in-the-Loop*).

**Audiencia:** Evaluadores académicos, musicólogos, directores de coro/orquesta, transcriptores y desarrolladores.

---

## 2. Contrato de API y Dependencias
- `GET /health`: Comprueba el estado del backend para mostrar un badge de disponibilidad en tiempo real (`Online · API v1.0.0` o `Offline`).
- `GET /version`: Muestra la versión del contrato OpenAPI y del sistema.

---

## 3. Anatomía Visual y Secciones

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza           [Pipeline]  [Arquitectura]  [Métricas]  [Tesis Docs]        [Iniciar Sesión] |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   Cadenza Studio Pro                                                                             |
|   Digitalización asistida de partituras con rigor científico.                                    |
|   La sinergia entre visión artificial end-to-end y corrección editorial inmutable.               |
|                                                                                                  |
|   [ Acceder a la Plataforma ➔ ]        [ Ver Documentación de Arquitectura ]                     |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
| SECCIÓN: El Pipeline Científico (Diagrama Interactivo)                                          |
|                                                                                                  |
|  [ Escaneo de Partitura ] ➔ [ Inferencia OMR ] ➔ [ Validador Musical ] ➔ [ Atril Dual HITL ]    |
|       (PNG / JPEG)              (HOMR / GPU)       (Reglas sintácticas)    (Corrección humana)   |
|                                                                                    │             |
|                                                                                    ▼             |
|                                                                           [ Exportación Canónica]|
|                                                                           (MusicXML 4.0 / MIDI)  |
+--------------------------------------------------------------------------------------------------+
| SECCIÓN: Tres Pilares Diferenciales                                                              |
|                                                                                                  |
|  1. Autoridad Notacional      2. Trazabilidad Append-Only        3. Telemetría de Esfuerzo       |
|  OSMD renderiza el modelo     Cada corrección genera un          Mide segundos y clics reales    |
|  ScoreIR; no depende de       evento inmutable con base_seq      por compás para evaluar la      |
|  cajas flotantes sobre píxel. y autoría en servidor.            reducción de fatiga editorial.  |
+--------------------------------------------------------------------------------------------------+
| FOOTER: Enlaces al repositorio GitHub, ADRs, estado del servicio y autoría de la tesis.        |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Contenido

1. **Barra de Navegación Pública (Header):**
   - Logotipo `cadenza` en fuente monoespaciada minúscula.
   - Enlaces de salto suave: *Pipeline*, *Arquitectura*, *Tesis*.
   - Badge de estado del servidor (`GET /health`): punto verde esmeralda con texto `API v1 en línea`.
   - Botón CTA secundario: `Iniciar Sesión` que redirige a `/login`.
2. **Hero Section:**
   - Kicker superior en tipografía mono: `TESIS DE PREGRADO / INGENIERÍA · HUMAN-IN-THE-LOOP OMR`.
   - Título principal en tipografía `Newsreader` (Serif de alto contraste editorial): *«La dignidad de la edición crítica musical unida a la precisión de la inteligencia artificial.»*
   - Párrafo de bajada en `Geist Sans` explicando la superación de los errores sutiles del OMR tradicional.
   - Botón primario: Blanco puro (`#FFFFFF`) con texto negro (`#0C0D0F`), radio `6px`: `Entrar al Espacio de Trabajo ➔`.
3. **Pipeline Interactivo (Demostración Visual):**
   - Visualizador de 4 pasos interactivos que ilustra cómo una partitura de Bach pasa de escaneo a MusicXML verificado.
   - Sin animaciones de rebote; transiciones sobrias de 150ms al pasar el ratón.
4. **Resumen de Resultados y Rigor de la Tesis:**
   - Cita explícita a la verificación empírica contra la verdad de referencia (referencia a `docs/PROJECT_STATE.md`).
5. **Footer Institucional:**
   - Enlaces a la Universidad, repositorio de GitHub, documentación de ADRs y licencia de código.

---

## 5. Estados de la Pantalla
- **Normal / Disponible:** Servidor activo, botón de acceso operativo.
- **Servidor Desconectado:** El badge del header muestra `Servidor en mantenimiento` en color ámbar neutro. El botón de login permanece disponible pero avisa de modo offline.

---

## 6. Atajos de Teclado
- <kbd>Enter</kbd>: En el Hero, avanza directamente a `/login`.
- <kbd>Tab</kbd>: Recorrido accesible secuencial de enlaces con borde de foco cobalto de 2px.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Destellos mágicos o iconos de varita (✨).
- **Prohibido:** Falsos testimonios o logotipos ficticios de clientes comerciales; es una tesis académica seria.
- **Prohibido:** Gráficos circulares con porcentajes inventados de "99.9% precisión de IA".
- **Prohibido:** Degradados púrpuras y efectos borrosos de neón.
