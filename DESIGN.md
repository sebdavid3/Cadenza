---
name: Cadenza Studio Pro
description: Sistema de diseño visual sobrio, de alta densidad y dark mode nativo para la suite de digitalización OMR y banco de trabajo HITL Cadenza.
colors:
  background: "#0C0D0F"
  surface-panel: "#141519"
  surface-elevated: "#1A1C22"
  surface-subtle: "#242731"
  surface-hover: "rgba(255, 255, 255, 0.04)"
  surface-active: "rgba(255, 255, 255, 0.07)"
  border-subtle: "rgba(255, 255, 255, 0.08)"
  border-medium: "rgba(255, 255, 255, 0.16)"
  border-focus: "#2563EB"
  text-primary: "#F3F4F6"
  text-secondary: "#9CA3AF"
  text-muted: "#6B7280"
  accent-primary: "#2563EB"
  accent-hover: "#1D4ED8"
  accent-contrast: "#FFFFFF"
  semantic-warning: "#D97706"
  semantic-warning-bg: "rgba(217, 119, 6, 0.12)"
  semantic-warning-border: "rgba(217, 119, 6, 0.3)"
  semantic-error: "#DC2626"
  semantic-error-bg: "rgba(220, 38, 38, 0.12)"
  semantic-error-border: "rgba(220, 38, 38, 0.3)"
  semantic-success: "#10B981"
  semantic-success-bg: "rgba(16, 185, 129, 0.12)"
  semantic-success-border: "rgba(16, 185, 129, 0.3)"
  music-selection: "rgba(37, 99, 235, 0.22)"
  music-cursor: "#2563EB"
typography:
  display:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "clamp(2.25rem, 5vw, 3.5rem)"
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Geist Sans, DM Sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Geist Sans, DM Sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Geist Sans, DM Sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  body-dense:
    fontFamily: "Geist Sans, DM Sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  label:
    fontFamily: "Geist Sans, DM Sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "0.04em"
  mono:
    fontFamily: "Geist Mono, JetBrains Mono, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  mono-number:
    fontFamily: "Geist Mono, JetBrains Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "0.02em"
rounded:
  none: "0px"
  xs: "2px"
  sm: "4px"
  md: "6px"
  lg: "8px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  base: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent-contrast}"
    textColor: "{colors.background}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.text-primary}"
    textColor: "{colors.background}"
    rounded: "{rounded.md}"
  button-accent:
    backgroundColor: "{colors.accent-primary}"
    textColor: "{colors.accent-contrast}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  button-secondary:
    backgroundColor: "{colors.surface-elevated}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
  input-field:
    backgroundColor: "{colors.surface-elevated}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  card-panel:
    backgroundColor: "{colors.surface-panel}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "16px"
  badge-pill:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
---

# Cadenza Studio Pro — Sistema de Diseño Visual

## Overview

Cadenza Studio Pro es el sistema de diseño visual de la plataforma Cadenza. Está inspirado en los estándares de excelencia de herramientas profesionales de alta densidad como **Linear**, **Ableton Live**, **Dorico** y **Figma**.

El sistema está concebido para profesionales (transcriptores musicales, musicólogos e investigadores en ciencias de la computación) que operan en sesiones de trabajo prolongadas e intensivas. Su lenguaje es sobrio, quirúrgico, con máxima densidad de datos útiles y libre de distracciones visuales o clichés tecnológicos.

### Principios Fundamentales:
1. **Densidad y Ergonomía Profesional:** Maximizar la información visible sin saturar visualmente. La jerarquía se expresa mediante espaciado de precisión y contraste tonal, no mediante márgenes vacíos inflados.
2. **Dark Mode Nativo:** Toda la suite opera de manera nativa en modo oscuro (#0C0D0F). El fondo profundo y la tonalidad fría atenúan la fatiga lumínica ocular durante la comparación continua de partituras.
3. **Economía Cromática:** La interfaz permanece neutra y monótona por defecto. El color es un recurso escaso reservado exclusivamente para la semántica musical, los estados de error y las acciones primarias de interacción.
4. **Respeto a la Ortografía Musical:** El software habla la lengua técnica de la notación simbólica (compases, voces, alteraciones canónicas, fracciones de pulso y claves), desterrando terminologías acústicas o aproximaciones no musicales.

---

## Colors

La paleta cromática se estructura en capas tonales de profundidad sobre negro ónice, complementadas con un acento de interacción cobalto y una escala semántica de advertencia, error y validación musical.

### Neutros y Superficies
- **App Shell / Fondo General:** `#0C0D0F` (Ónice profundo). El sustrato fundamental de la aplicación; otorga calma visual y un marco cinemático de alto contraste.
- **Superficies Secundarias y Paneles:** `#141519`. Utilizado en barras laterales, atril de visualización, cabeceras de paneles fijos e inspectores.
- **Superficies Elevadas, Filas e Inputs:** `#1A1C22`. Fondo de tarjetas interactivas, modales de diálogo, campos de formulario, dropdowns y estados de descanso de filas de tabla.
- **Superficies Sutiles:** `#242731`. Utilizado para contenedores internos, cajas de atajos (`kbd`) y badges neutros.
- **Bordes y Separadores Sutiles:** `rgba(255, 255, 255, 0.08)`. Líneas nítidas de 1px que delimitan todas las divisiones estructurales y marcos de panel sin generar ruido visual.
- **Bordes Medios / Hover:** `rgba(255, 255, 255, 0.16)`. Estados interactivos de descanso en inputs y tarjetas.
- **Borde de Foco Accesible:** `#2563EB`. Anillo exterior de 2px con desplazamiento para todo elemento enfocado por teclado (`focus-visible`).

### Textos y Tipografía
- **Texto Primario:** `#F3F4F6` (Gris 100). Títulos, valores de notas, compases, texto activo e información principal.
- **Texto Secundario:** `#9CA3AF` (Gris 400). Etiquetas descriptivas, metadatos, nombres de columnas y cabeceras de tabla.
- **Texto Atenuado (Muted):** `#6B7280` (Gris 500). Marcadores de posición (*placeholders*), compases inactivos y códigos de tecla de atajo.

### Acentos de Interacción
- **Acento Primario (Cobalto):** `#2563EB` (Cobalt Blue). Señalizador táctico de interacción activa, cursor de reproducción musical en transporte y resaltado de selección.
- **Hover de Acento:** `#1D4ED8`. Estado presionado o hover sobre controles de acento.
- **Blanco Puro de Alto Contraste:** `#FFFFFF`. Utilizado exclusivamente para el botón de acción principal de la pantalla (`button-primary`), logrando prominencia inmediata sin degradados artificiales.

### Estados Semánticos
- **Advertencia Musical:** `#D97706` (Ámbar).
  - *Fondo:* `rgba(217, 119, 6, 0.12)` | *Borde:* `rgba(217, 119, 6, 0.30)`.
  - *Uso:* Inconsistencias de métrica en compás, notas con ligaduras abiertas o discrepancias métricas detectadas por el validador sintáctico.
- **Error / Conflicto:** `#DC2626` (Rojo Carmesí).
  - *Fondo:* `rgba(220, 38, 38, 0.12)` | *Borde:* `rgba(220, 38, 38, 0.30)`.
  - *Uso:* Violaciones de reglas del dominio musical (compases sobrellenados), conflicto de concurrencia optimista (`409 Conflict`) o fallos de red/servidor.
- **Verificado / Completado:** `#10B981` (Verde Esmeralda).
  - *Fondo:* `rgba(16, 185, 129, 0.12)` | *Borde:* `rgba(16, 185, 129, 0.30)`.
  - *Uso:* Sesiones finalizadas y cerradas (`closed`), partituras verificadas en archivo histórico y exportaciones completadas con éxito.
- **Selección y Reproducción Musical:**
  - *Selección de Nota/Compás:* `rgba(37, 99, 235, 0.22)` con contorno `1px solid #2563EB`.
  - *Cursor de Audio (Tone.js):* Barra vertical de 2px en `#2563EB` que avanza de manera fluida compás por compás.

### Reglas Nombradas de Color
- **The Signal-to-Ink Rule (Regla de la Tinta Útil):** Los colores de acento y semánticos no deben ocupar más del 5% del área total de cualquier pantalla en estado de reposo. El fondo debe permanecer neutro y oscuro para que el foco visual recaiga 100% sobre la partitura y los datos.
- **The Pure Black Absence Rule (Ausencia de Negro Absoluto):** Nunca utilizar `#000000` puro para las superficies de la interfaz. El tono base `#0C0D0F` conserva la atmósfera de profundidad y permite que las líneas de 1px `rgba(255, 255, 255, 0.08)` se perciban con nitidez óptica.

---

## Typography

El sistema tipográfico combina tres familias con propósitos estrictamente definidos:

1. **Tipografía Editorial Solemne (`Newsreader` / Garamond):**
   - *Rol:* Encabezados solemnes, títulos de la Landing Page institucional y carátulas de obras en el archivo histórico. Otorga dignidad académica, rigor musicológico y tradición tipográfica de conservatorio.
2. **Tipografía de Interfaz Moderna (`Geist Sans` / `DM Sans`):**
   - *Rol:* Interfaz general, etiquetas de paneles, navegación, formularios y botones. Se elige una sans-serif geométrica contemporánea con excelente legibilidad en tamaños reducidos (se evita conscientemente Inter estándar para dar carácter propio a la suite).
3. **Tipografía Técnica Monospace (`Geist Mono` / `JetBrains Mono`):**
   - *Rol:* Cifras de compases, fracciones de pulso (`1/4`, `3/8`), marcas temporales de auditoría, nombres canónicos de notas (`C#4`, `Bb3`), claves JSON, códigos de error y atajos de teclado (`Ctrl+K`, `Esc`).

### Escala Tipográfica de la Suite

| Nivel | Familia | Tamaño | Peso | Interlínea | Tracking | Uso |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Display** | Editorial Serif | `clamp(2.25rem, 5vw, 3.5rem)` | 400 | 1.15 | -0.02em | Título principal de la Landing institucional. |
| **Headline** | UI Sans | `1.25rem` (20px) | 600 | 1.30 | -0.015em | Título de vistas principales, modales y dashboard. |
| **Title** | UI Sans | `1.00rem` (16px) | 500 | 1.40 | -0.01em | Cabeceras de panel, títulos de sección en inspector. |
| **Body** | UI Sans | `0.875rem` (14px) | 400 | 1.50 | normal | Textos explicativos, descripciones y diálogos. |
| **Body Dense** | UI Sans | `0.8125rem` (13px) | 400 | 1.40 | normal | Filas de tablas densas, listas de hallazgos y árbol. |
| **Label / Kicker** | UI Sans | `0.75rem` (12px) | 600 | 1.25 | +0.04em | Etiquetas en mayúsculas, roles de usuario, badges. |
| **Mono** | Monospace | `0.8125rem` (13px) | 400 | 1.45 | normal | Valores canónicos (`pitch`, `duration`), logs y diff. |
| **Mono Number** | Monospace | `0.75rem` (12px) | 500 | 1.25 | +0.02em | Número de compás, BPM, latencias (ms) y chips `kbd`. |

### Reglas Nombradas de Tipografía
- **The Tabular Precision Rule (Regla de Cifras Tabulares):** Todo número representativo de métricas, duraciones musicales, compases o latencias en milisegundos debe renderizarse obligatoriamente con cifras tabulares (`font-variant-numeric: tabular-nums` o `font-feature-settings: "tnum"`), garantizando que las columnas numéricas no oscilen al actualizarse.
- **The Strict Metric Naming Rule:** Las alturas musicales deben escribirse en notación científica canónica anglosajona en mayúsculas con alteraciones canónicas (`C4`, `F#3`, `Bb5`, `A-2`), nunca con nombres descriptivos en minúsculas (`do4`, `fa sostenido`).

---

## Layout

### Cuícula Base y Espaciado
- El espaciado utiliza una escala estricta basada en múltiplos de **4px** (`4px`, `8px`, `12px`, `16px`, `24px`, `32px`, `48px`).
- Para interfaces de alta densidad operacional (Atril HITL, tablas e inspectores), el ritmo espacial preferido es compacto: márgenes de `8px` y `12px` entre controles hermanos.

### Arquitectura de Shell de la Aplicación
1. **Header Persistente (48px de alto):**
   - Logotipo y versión de contrato (`Cadenza v1.0.0`).
   - Indicador de estado de conexión con el backend (`GET /health`).
   - Disparador de la Command Palette persistente (`Ctrl+K`).
   - Breadcrumbs de navegación de sesión y perfil de usuario activo con badge de rol (`transcriptor` o `investigador`).
2. **Área de Trabajo en Pantalla Completa (`100vh`):**
   - Sin scroll global en la ventana del navegador (`overflow: hidden` en el viewport raíz).
   - Cada panel o visor gestiona su propio scroll interno independiente mediante barras de desplazamiento delgadas y discretas.

### Anatomía del Banco de Trabajo HITL (Atril Dual)
- **División Principal (50 / 50 ajustable):**
  - **Panel Izquierdo — Visor de Escaneo Original:** Lienzo optimizado con aceleración por hardware para zoom suave, desplazamiento panorámico (*pan*) y vista 1:1 de la partitura fuente cargada vía `GET /sessions/{id}/image`.
  - **Panel Derecho — Atril Digital OSMD:** Visor SVG vectorial interactivo que renderiza la notación musical viva a partir del MusicXML compilado. Al hacer clic en un compás o nota, sincroniza automáticamente la selección con el inspector.
- **Dock Lateral Plegable Derecho (320px de ancho):**
  - Pestaña 1: **Hallazgos (`Findings`):** Lista filtrable de errores sintácticos detectados automáticamente, con severidad y atajos para descartar (*dismiss*) o restaurar (*restore*).
  - Pestaña 2: **Inspector de Evento:** Edición quirúrgica del elemento seleccionado (altura, duración fraccionaria, alteración, ligadura).
  - Pestaña 3: **Registro de Edición:** Historial *append-only* en orden cronológico inverso con opción de deshacer en servidor (*undo*).
- **Barra de Transporte Inferior (44px de alto):**
  - Controles de reproducción con Tone.js (Play/Pause, Rebobinar, Repetición en bucle).
  - Selector de tempo dinámico en tiempo real (BPM: 40 a 240) con traducción matemática de fracciones de pulso a segundos.
  - Indicador de compás actual y tiempo transcurrido en cifras monoespaciadas tabulares.

---

## Elevation & Depth

El sistema descarta los degradados dramáticos y las sombras difusas pesadas en favor de un modelo de **capas tonales superpuestas (Tonal Layering)** y **delimitación por bordes de 1px**:

- **Nivel 0 (Base / Shell):** `#0C0D0F`. Fondo inerte.
- **Nivel 1 (Superficies de Panel):** `#141519` con borde de `1px solid rgba(255, 255, 255, 0.08)`. Paneles laterales, visores de partitura y cajas de herramientas fijas.
- **Nivel 2 (Tarjetas y Elementos Elevados):** `#1A1C22` con borde de `1px solid rgba(255, 255, 255, 0.08)`. Tarjetas en dashboard, filas en hover y campos de entrada de formulario.
- **Nivel 3 (Modales, Diálogos y Command Palette):** `#1A1C22` elevado con fondo sutil `#242731`, borde de `1px solid rgba(255, 255, 255, 0.16)` y sombra ambiental suave:
  `box-shadow: 0 16px 36px -8px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(255, 255, 255, 0.10)`.

### Reglas Nombradas de Elevación
- **The Border-Over-Shadow Rule (Regla del Borde sobre la Sombra):** La separación visual y la jerarquía entre paneles vecinos en el mismo plano se define exclusivamente mediante bordes de 1px (`rgba(255, 255, 255, 0.08)`). Las sombras se reservan únicamente para elementos flotantes transitorios que rompen el plano (modales, popovers y menús desplegables).

---

## Shapes

La geometría de Cadenza Studio Pro es sobria, técnica y de aristas controladas. Se evitan radios excesivamente redondeados que infantilizan la herramienta:

- **Borde Nulo (`none` / 0px):** Cuadrícula de paneles adyacentes y divisores estructurales.
- **Radio Micro (`xs` / 2px):** Chips de teclas de atajo (`<kbd>`) y marcadores de posición sobre el pentagrama.
- **Radio Sutil (`sm` / 4px):** Celdas interactivas de tabla, botones miniatura de transporte y selectores de herramientas.
- **Radio Estándar (`md` / 6px):** Botones generales, campos de texto (inputs), selects de formulario y tarjetas de hallazgos.
- **Radio de Panel (`lg` / 8px):** Modales flotantes, paneles contenedores del dashboard y tarjetas del archivo histórico.
- **Radio Píldora (`full` / 9999px):** Reservado estrictamente para badges de estado (`transcribed`, `closed`, `warning`, `error`).

---

## Components

### 1. Barra de Navegación y Command Palette (`Ctrl+K`)
- **Disparador Global:** Siempre visible en el header superior con buscador y chip de atajo genérico y multiplataforma `Ctrl+K` (estándar universal de teclado, libre de glifos o símbolos propietarios de sistemas operativos).
- **Ventana de Comandos:** Modal centrado de 560px con buscador difuso instantáneo:
  - Navegación directa entre las 11 vistas del sistema.
  - Búsqueda de partituras por título, compositor o ID de sesión.
  - Invocación de operaciones rápidas (`Exportar MusicXML`, `Deshacer edición`, `Reabrir sesión`, `Ir al compás N`).
  - Salida inmediata con la tecla `Escape`.

### 2. Tablas de Datos de Alta Densidad (Dashboard y Gestión)
- **Altura de Fila:** Compacta (36px a 40px), optimizada para visualizar decenas de registros simultáneos.
- **Separación:** Línea inferior de `1px solid rgba(255, 255, 255, 0.06)`.
- **Fondo:** `#141519` en reposo; transición rápida a `#1A1C22` al posar el cursor (*hover*).
- **Columnas:** Ordenables por cabecera interactiva con glifo discreto de ordenación (`▲ / ▼`), alineación numérica a la derecha y badges de estado en píldora compacta.

### 3. Botones y Chips de Atajo
- **Botón Primario de Cierre / Acción (`button-primary`):** Fondo blanco `#FFFFFF`, texto `#0C0D0F`, peso semibold, radio 6px. Máxima claridad y contraste.
- **Botón de Acento (`button-accent`):** Fondo azul cobalto `#2563EB`, texto blanco `#FFFFFF`. Para acciones de inferencia OMR o confirmación intermedia.
- **Botón Secundario (`button-secondary`):** Fondo `#1A1C22`, borde `1px solid rgba(255, 255, 255, 0.08)`, texto `#F3F4F6`.
- **Botón Fantasma (`button-ghost`):** Fondo transparente, texto `#9CA3AF`, hover con fondo `rgba(255, 255, 255, 0.05)`.
- **Chip de Teclado Integrado (`<kbd>`):** Todo botón con atajo muestra a su derecha un chip en miniatura (`background: #242731; border: 1px solid rgba(255, 255, 255, 0.12); font-family: monospace; font-size: 10px; padding: 1px 4px; border-radius: 2px`).

### 4. Modales Compactos y Diálogos de Confirmación
- **Geometría:** Centrados horizontal y verticalmente, ancho máximo controlado (440px a 520px).
- **Fondo y Filtro:** Fondo `#1A1C22` sobre un telón (*backdrop*) oscuro `rgba(12, 13, 15, 0.8)` con desenfoque de fondo sutil (`backdrop-filter: blur(4px)`).
- **Comportamiento:** Foco atrapado de forma accesible dentro del modal y cierre garantizado con `Escape` o clic exterior.

### 5. Tarjetas de Hallazgos y Lista de Validación (`FindingsPanel`)
- **Estructura:** Lista vertical compacta con separación de 6px.
- **Indicador de Gravedad:** Barra lateral izquierda de 3px con color semántico puro: rojo `#DC2626` para errores métricos insalvables; ámbar `#D97706` para advertencias de lectura.
- **Interacción:** Clic en la tarjeta centra automáticamente el compás y selecciona la nota afectada en el atril OSMD. Incluye botones de un clic para descartar falso positivo (`dismiss`) o restaurar.

### 6. Inspector de Eventos Musicales (`EventInspector`)
- **Disposición:** Formulario en cuadrícula de dos columnas densas.
- **Controles Especializados:**
  - Selector de Altura Canónica: Input de texto con validación en tiempo real (`C#4`, `Db5`) y teclado de notas en pantalla.
  - Selector de Duración: Botones de figuras canónicas (redonda, blanca, negra, corchea, semicorchea) mapeados a valores fraccionarios (`1`, `1/2`, `1/4`, `1/8`, `1/16`).
  - Interruptores de Ligadura y Puntos de Aumento.
  - Visualización del identificador del evento (`part`, `staff`, `measure`, `voice`, `event_index`) en tipografía monoespaciada.

### 7. Barra de Transporte Musical (Tone.js)
- **Controles de Reproducción:** Botones de reproducción/pausa con señalización de tecla de espacio (`Espacio`).
- **Control de Tempo:** Slider continuo y campo numérico editable en BPM (rango 40–240).
- **Indicador de Tiempo:** Compás actual, tiempo en pulso fraccionario y cronómetro acumulado en cifras tabulares.

---

## Do's and Don'ts

### Do (Directrices Obligatorias):
- **Do:** Usar Dark Mode nativo (#0C0D0F) como única apariencia admitida en toda la suite.
- **Do:** Diseñar con teclado en mente: cada acción crítica en el atril debe contar con un atajo claramente señalizado mediante chips `<kbd>`.
- **Do:** Utilizar cifras tabulares (`tabular-nums`) en cualquier representación de métricas, compases, latencias de esfuerzo y marcas de tiempo.
- **Do:** Separar los paneles con líneas sutiles de 1px (`rgba(255, 255, 255, 0.08)`) y capas tonales, evitando sombras difusas pesadas.
- **Do:** Mantener la notación musical renderizada en OSMD como el centro de mando y autoridad semántica, utilizando la imagen del escaneo como referencia estática fiel.
- **Do:** Proporcionar respuesta inmediata con toasts o alertas compactas ante conflictos de concurrencia optimista (`409 Conflict`), facilitando la recarga de sesión sin pérdida de datos.
- **Do:** Usar terminología musical rigurosa en español: *compás*, *alteración*, *becuadro*, *duración de pulsos*, *voz*, *clave de sol/fa/do*, *armadura*.

### Don't (Anti-patrones Estrictamente Prohibidos):
- **Don't:** **CERO destellos, chispas o estrellas mágicas (✨, 🌟)** en botones, encabezados, rótulos de modelos o badges de la suite. Cadenza es una herramienta científica, no un asistente conversacional de consumo.
- **Don't:** **CERO gráficos de dona circulares de "AI Confidence Score"** ni porcentajes inventados de certeza sobre la partitura. (HOMR no genera probabilidades calibradas ni confianzas por nota).
- **Don't:** **CERO degradados púrpuras, fucsias o halos de neón estilo videojuego** (`#8B5CF6`, `#EC4899`, etc.). El acento oficial es exclusivamente el azul cobalto `#2563EB` y el blanco de alto contraste `#FFFFFF`.
- **Don't:** **CERO parámetros acústicos irrelevantes en notación simbólica** (prohibido hablar de hercios, frecuencias en Hz, waveforms o archivos `.wav`; la notación se expresa en alturas canónicas, figuras y compases).
- **Don't:** **CERO promesas de recuadros o resaltados de notas individuales sobre la imagen original con el motor HOMR** (de acuerdo con INV-0001 y la deuda técnica D4, HOMR devuelve siempre `bbox: null`).
- **Don't:** **CERO fuentes genéricas estándar como Inter o Roboto** para la personalidad global de la marca. Usar la combinación establecida de `Newsreader` para lo editorial, `Geist Sans / DM Sans` para la interfaz y `Geist Mono / JetBrains Mono` para datos técnicos.
- **Don't:** **CERO márgenes gigantescos o interfaces infladas estilo aplicación móvil para tabletas.** Cadenza es un software de escritorio para expertos donde la densidad de información y el espacio útil de partitura son prioritarios.
