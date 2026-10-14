# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

- **Frontend:** React 18 (`apps/web`), TypeScript 5.5 (modo estricto), Vite 5, TanStack React Query v5, Zustand v4.
- **Renderizado y Audio:** OpenSheetMusicDisplay (OSMD) para renderizado vectorial interactivo de MusicXML; Tone.js para síntesis de audio y reproducción sincronizada con cálculo dinámico de tempo en cliente.
- **Backend:** Python 3.12, FastAPI (servidor ASGI Uvicorn), SQLAlchemy 2.0 en modo asíncrono, migraciones secuenciales con Alembic.
- **Bases de Datos y Almacenamiento:** SQLite con driver `pysqlite` para desarrollo local ágil; PostgreSQL para integración continua (CI) y despliegue productivo; sistema de archivos local para artefactos de imagen y exportaciones.
- **Motores OMR:**
  - `HOMREngine` (neuronal end-to-end sobre ONNX Runtime con aceleración opcional CUDA/GPU).
  - `FakeOMREngine` (adaptador sintético determinista para pruebas unitarias y desarrollo desacoplado).
- **Formatos de Intercambio:** MusicXML 4.0, MIDI 1.0 estándar, OpenAPI 3.1 con cabecera obligatoria `X-API-Version: 1.0.0`.

## Users

1. **Transcriptor Musical (Operador Primario):**
   - **Situación:** Sesiones intensivas de transcripción y corrección editorial frente al ordenador, con frecuencia de varias horas continuas de análisis comparativo entre la imagen de la partitura original y la notación digital.
   - **Objetivo:** Digitalizar y subsanar discrepancias del OMR con la máxima velocidad, fiabilidad y comodidad. Requiere atajos de teclado exhaustivos (edición sin ratón), baja fatiga visual mediante un entorno oscuro de alto contraste y certeza absoluta de que el archivo final exportado respeta la ortografía musical canónica.
2. **Investigador / Administrador Científico:**
   - **Situación:** Supervisión de proyectos de investigación musicológica o de ciencias de la computación, evaluación del rendimiento de modelos de visión artificial y gestión del equipo de transcripción.
   - **Objetivo:** Monitorear el progreso global, evaluar métricas objetivas de esfuerzo cognitivo (duración de la sesión, latencia hasta la primera intervención humana, distribución de correcciones por compás), auditar el historial inmutable de cambios (`audit log`) y curar datasets etiquetados para el reentrenamiento offline de modelos OMR (aprendizaje activo).

## Product Purpose

Cadenza es una suite web integral y banco de trabajo científico Human-in-the-Loop (HITL) diseñada para la digitalización asistida de partituras manuscritas e impresas, combinando el reconocimiento óptico de música (OMR) con la corrección humana de alta precisión.

El producto resuelve la brecha existente entre los motores OMR probabilísticos —que cometen errores sutiles pero destructivos en alturas, alteraciones y ritmos— y las exigencias rigurosas de la edición musical académica. Cadenza convierte la corrección humana en un proceso estructurado, ergonómico y científicamente trazable, donde cada clic o pulsación de tecla contribuye tanto a la obtención de una partitura impecable (MusicXML/MIDI) como a la generación de datos para la evaluación y reentrenamiento de la inteligencia artificial.

## Positioning

A diferencia de las aplicaciones comerciales cerradas de escaneo de partituras (como SmartScore o PhotoScore) y de los prototipos académicos aislados en notebooks:
- **Trazabilidad Científica Inmutable:** El documento OMR original (`ScoreDocument`) nunca se muta; cada cambio humano se almacena en un registro de ediciones *append-only* (`EditOp`) con control de concurrencia optimista (`base_seq`).
- **Telemetría de Esfuerzo Editorial Real:** Cuantifica y almacena el esfuerzo cognitivo del transcriptor (tiempo real de trabajo, latencia de detección del primer error y densidad de intervenciones por compás), permitiendo comparar rigurosamente la usabilidad y la reducción de carga de trabajo entre diferentes motores OMR.
- **Autoridad de la Notación sobre el Píxel:** Separa con rigor la imagen gráfica de la estructura semántica musical (`ScoreIR`), garantizando que la reproducción auditiva (Tone.js) y la exportación (MusicXML 4.0) dependan exclusivamente de datos canónicos verificados.

## Operating Context

Cadenza se ejecuta como una aplicación web de escritorio profesional orientada a pantallas panorámicas (resolución mínima recomendada: 1920×1080), donde el usuario interactúa simultáneamente con herramientas visuales, auditivas y de teclado.

### Arquitectura de Vistas (Ecosistema Completo de 11 Vistas):

1. **Home / Landing Institucional:**
   - *Propósito:* Presentación formal de la plataforma, fundamentación científica de la tesis, demostración del flujo del pipeline (Imagen → OMR → HITL → MusicXML) y acceso a la aplicación.
   - *Público:* Nuevos visitantes, evaluadores académicos y usuarios que inician sesión.
2. **Autenticación y Acceso (`/login`, `/auth/password`):**
   - *Propósito:* Identificación segura mediante Bearer JWT y cambio controlado de credenciales.
   - *Regla operativa:* Conforme a ADR-0012, no existe autorregistro público ni recuperación por correo; las cuentas son creadas por investigadores mediante CLI o panel de administración.
3. **Dashboard / Tablero de Sesiones (`/dashboard`):**
   - *Propósito:* Centro de mando para transcriptores e investigadores.
   - *Componentes:* Resumen de actividad reciente, selector de vista (tabla de alta densidad o cuadrícula de tarjetas con miniaturas de escaneo), filtrado avanzado por estado (`transcribed`, `in_progress`, `closed`), motor OMR utilizado y buscador por obra o compositor.
4. **Ingesta y Nueva Partitura (`/transcribe`):**
   - *Propósito:* Punto de entrada de documentos.
   - *Componentes:* Dropzone para imágenes (PNG, JPEG), previsualización del escaneo, selector de motor OMR (`HOMR` con opción GPU vs `FakeOMREngine`), monitor de estado de inferencia síncrona y redirección automática al banco de trabajo tras completar el procesamiento.
5. **Banco de Trabajo HITL (`/sessions/:id`):**
   - *Propósito:* Núcleo operativo del sistema (Atril Dual).
   - *Componentes:*
     - *Atril Dual Dividido:* Panel izquierdo con escaneo original en alta resolución (zoom, pan, centrado); panel derecho con visor vectorial interactivo OSMD.
     - *Barra de Transporte Musical:* Reproducción sincronizada con Tone.js, selector dinámico de tempo (BPM), posición métrica y cursor de seguimiento sobre compás activo.
     - *Panel de Hallazgos (`findings`):* Lista de anomalías detectadas por reglas sintácticas deterministas (errores de duración de compás, alteraciones no resueltas), con salto directo al evento y botones de descarte/restauración.
     - *Inspector de Eventos:* Edición atómica de alturas canónicas (`A`-`G`), duraciones racionales exactas, claves, armaduras y ligaduras.
     - *Barra de Herramientas y Atajos:* Historial de ediciones (*undo* en servidor), guardado y señalización de atajos de teclado.
6. **Resumen de Cierre y Exportación (`/sessions/:id/finalize`):**
   - *Propósito:* Puerta de salida editorial y formalización de finalización.
   - *Componentes:* Visualización de telemetría de esfuerzo (tiempo total invertido, compases con mayor densidad de corrección), comprobación de integridad y descarga de artefactos validados (MusicXML 4.0, MIDI 1.0, informe de auditoría).
7. **Biblioteca / Archivo Histórico (`/library`):**
   - *Propósito:* Repositorio de obras completamente digitalizadas, verificadas y cerradas.
   - *Componentes:* Catálogo permanente de solo lectura, visor de partitura completa para consulta rápida, búsqueda facetada por metadatos musicales y descarga directa de archivos terminados.
8. **Historial de Auditoría y Diff (`/sessions/:id/history`):**
   - *Propósito:* Inspección forense y trazabilidad científica.
   - *Componentes:* Visualizador del log *append-only* inmutable con marcas de tiempo precisas y autores asignados. Comparador visual (*diff*) entre el árbol OMR original crudo y el estado resultante tras la intervención humana.
9. **Gestión de Usuarios y Roles (`/admin/users`):**
   - *Propósito:* Consola administrativa restringida a investigadores.
   - *Componentes:* Directorio de usuarios, creación de cuentas para transcriptores, asignación de roles (`investigador` vs `transcriptor`), restablecimiento de contraseñas y auditoría de sesiones activas.
10. **Métricas del Sistema y Evaluación OMR (`/admin/metrics`):**
    - *Propósito:* Tablero analítico para la experimentación de la tesis.
    - *Componentes:* Métricas comparativas de exactitud e inferencia entre motores OMR, latencias de procesamiento, tiempos medios de corrección por compás y tasa de hallazgos corregidos vs falsos positivos descartados.
11. **Centro de Datasets y Modelos (`/admin/datasets`):**
    - *Propósito:* Gestión de muestras para aprendizaje activo offline.
    - *Componentes:* Selección y empaquetado de sesiones corregidas donde hubo mayor discrepancia entre el OMR y el transcriptor, exportación de tripletas de entrenamiento (imagen, MusicXML corregido, log de corrección) para reentrenamiento de modelos neuronales.

## Capabilities and Constraints

- **Contrato de API v1 Congelado:** Toda la comunicación frontend-backend se rige por la especificación OpenAPI 3.1 v1.0.0 inyectando la cabecera `X-API-Version: 1.0.0`.
- **Concurrencia Optimista Estricta:** Las ediciones (`POST /sessions/{id}/edits`) requieren el parámetro `base_seq`. Si el servidor detecta una discrepancia con la secuencia actual, responde `409 Conflict` para prevenir sobreescrituras accidentales.
- **Operaciones de Edición Atómicas Tipadas:** Conforme a ADR-0017, las ediciones se limitan a `SetPitch`, `SetDuration`, `SetAccidental`, `InsertEvent`, `DeleteEvent`, `SetClef` y `SetKey`. El servidor valida canónicamente la carga útil `after` y captura un `snapshot_before` inmutable.
- **Restricción de Cajas Delimitadoras (`bbox`) y Confianza:**
  - En `HOMREngine` real, `bbox` y `confidence` son siempre `null` (deuda técnica D4, INV-0001). El frontend no debe asumir ni prometer cajas delimitadoras sobre la imagen original al usar HOMR.
  - La partitura renderizada vectorialmente en OSMD es la interfaz primaria de interacción y selección.
- **Cálculo Determinista de Tiempo:** El endpoint `GET /sessions/{id}/timing` proporciona las posiciones métricas en fracciones de pulso (`duration_beats`, `offset_beats`). El frontend con Tone.js es el responsable de traducir estas fracciones a segundos absolutos según el BPM seleccionado por el usuario.
- **Ciclo de Vida de Sesión:** Tras invocar `POST /finalize`, la sesión pasa a estado `closed` y rechaza nuevas ediciones con `409 SessionClosed`. Solo un investigador puede reabrirla (`POST /reopen`) bajo registro de auditoría explícito.

## Brand Commitments

- **Nombre:** Cadenza.
- **Subtítulo:** Suite de Digitalización Asistida de Partituras y Banco de Trabajo Human-in-the-Loop.
- **Voz y Tono:** Rigurosa, técnica, serena y de precisión quirúrgica ("Cadenza Studio Pro"). Habla el lenguaje de los transcriptores de conservatorio y los investigadores de ciencias de la computación.
- **Prohibición Estricta de Clichés de IA:**
  - Prohibido el uso de destellos, estrellas mágicas o chispas (✨) en botones, etiquetas o cabeceras.
  - Prohibidos los falsos indicadores circulares de "AI Confidence Score" o porcentajes engañosos de precisión.
  - Prohibidos los degradados púrpuras, violetas o halos de neón estilo videojuego.
  - Prohibida la inclusión de parámetros acústicos irrelevantes en la notación simbólica (cero Hz, cero archivos `.wav`; el sistema trabaja con alturas y figuras canónicas).

## Evidence on Hand

- Especificación de contrato OpenAPI 3.1 congelado: `docs/api/openapi.json`.
- Guía de integración de frontend y contratos de tipo: `docs/api/frontend-handoff.md`.
- Registro de 17 Decisiones de Arquitectura aceptadas: `docs/adr/ADR-0001` a `ADR-0017`.
- Documento de arquitectura integral del sistema: `docs/ARCHITECTURE.md` (v1.2).
- Bitácora de estado vivo, inventario de deuda técnica (D1 a D13) e investigaciones: `docs/PROJECT_STATE.md`.
- Tipos de TypeScript tipados estrictamente: `apps/web/src/types.ts`.
- Suite de pruebas de backend con 100% de éxito en pytest e integración continua en PostgreSQL.

## Product Principles

1. **La Notación Musical es la Autoridad Semántica:** La interacción, validación y corrección se fundamentan en el lenguaje musical formal (OSMD y MusicXML), nunca en aproximaciones cosméticas sobre la imagen.
2. **Cada Corrección es un Hecho Científico Inmutable:** Ningún dato se borra silenciosamente. El registro *append-only* garantiza reproducibilidad absoluta para la investigación empírica.
3. **Ergonomía de Teclado y Máxima Densidad de Información:** El transcriptor profesional no debe depender del ratón para el trabajo repetitivo. La pantalla debe maximizar el área útil de partitura y panel de datos sin elementos ornamentales superfluos.
4. **Honestidad y Transparencia Técnica:** El sistema muestra con exactitud lo que el motor OMR reconoció, sin simular certezas inexistentes ni maquillar errores con automatismos opacos.
5. **Preservación y Fidelidad de Exportación:** La salida a MusicXML 4.0 y MIDI 1.0 debe ser canónica y reproducible en cualquier software de notación estándar (Dorico, Finale, Sibelius, MuseScore) sin pérdida de estructura.

## Accessibility & Inclusion

- **Estándar:** WCAG 2.1 nivel AA para aplicaciones web ricas de escritorio.
- **Navegación Total por Teclado:** Toda acción de edición, navegación entre compases, cambio de paneles e invocación de comandos debe poder ejecutarse mediante atajos de teclado sin requerir puntero fino.
- **Indicadores de Foco Inequívocos:** Contorno visible de alto contraste (`#2563EB`) en todo elemento interactivo enfocado.
- **Ergonomía Visual:** Tema oscuro nativo diseñado para mitigar la fatiga ocular en jornadas prolongadas de lectura musical intensiva, con ratios de contraste superiores a 7:1 para elementos de estado crítico (errores, advertencias y selección activa).
