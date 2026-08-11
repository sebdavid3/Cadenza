# 03 — Validación Musical y Corrección de Errores

Reglas musicales automáticas, detección y corrección de errores en la salida de un OMR
(notas fuera de compás, duraciones inválidas, armaduras inconsistentes, voces que no cierran, etc.).
Alimenta el **Motor de Validación** de Cadenza, el componente central del aporte del proyecto.

> ⚠️ Este es el tema con **menos literatura consolidada específica de OMR** — y justamente ahí está el
> aporte de Cadenza. Las fichas de herramientas/formatos son seguras; los papers marcados como
> "verificar" son candidatos a confirmar.

## Índice

| ID | Título | Año | Relevancia |
|---|---|---|---|
| VAL-001 | music21 — toolkit para análisis musical computacional | 2010 | Alta |
| VAL-002 | Language models para post-procesamiento de OMR | 2022–2023 | Media (verificar) |

## Fichas

### [VAL-001] music21: A Toolkit for Computer-Aided Musicology and Symbolic Music Data
- **Autores:** Michael Scott Cuthbert, Christopher Ariza
- **Año / Venue:** 2010, Proc. de la 11.ª ISMIR
- **DOI / URL:** https://web.mit.edu/music21/ · https://github.com/cuthbertLab/music21
- **Tags:** music21, teoría musical, análisis, python, musicxml
- **Abstract (resumen parafraseado):**
  > music21 es un toolkit Python para musicología computacional: parsea y escribe MusicXML y otros
  > formatos, y ofrece herramientas de teoría musical (intervalos, tonalidad, acordes, duraciones,
  > compases) y análisis programático de partituras simbólicas.
- **Relevancia para Cadenza:** Alta — candidato natural para implementar el **motor de validación**:
  reglas de compás, duraciones, armaduras y sintaxis musical sobre la salida MusicXML de oemer.
- **Notas / ideas:**
  - Explorar las validaciones ya incluidas (p. ej. verificación de compases, voces, corchetes).
  - Evaluar performance al validar muchas partituras en lote.
  - Si se descarta music21, documentar por qué (curva de aprendizaje, overhead, limitaciones).

### [VAL-002] Language models aplicados a la corrección de salidas de OMR
- **Autores:** Ríos-Vila, A., et al. (grupo de la U. de Alicante)
- **Año / Venue:** aprox. 2022–2023, ISMIR / IJDAR — **verificar**
- **DOI / URL:** pendiente de confirmar
- **Tags:** omr, post-procesamiento, language models, corrección
- **Abstract (resumen parafraseado):**
  > Línea de trabajo que usa modelos de lenguaje musical (n-gramas / transformers sobre secuencias
  > simbólicas) para corregir o reordenar las hipótesis de un OMR end-to-end, aprovechando el
  > contexto musical global.
- **Relevancia para Cadenza:** Media — enfoque complementario (o alternativo) al motor de validación
  basado en reglas; comparar ventajas/desventajas para el documento de tesis.
- **Notas / ideas:**
  - Confirmar la referencia exacta y leerla antes de decidir la estrategia de validación.
  - Posible sección del estado del arte: "corrección post-OMR basada en modelos de lenguaje" vs.
    "validación por reglas".

## Líneas de búsqueda sugeridas (aún sin ficha)

1. **Reglas de teoría musical en sistemas de transcripción:** buscar "music notation error detection",
   "grammar-based music validation", "score error detection symbolic".
2. **Verificación de consistencia rítmica/métrica:** "rhythmic parsing music", "meter detection symbolic music".
3. **Herramientas de validación:** además de music21, revisar `Humdrum`/`Humdrum Toolkit` (comandos de
   verificación) y `MuseScore` (que repara automáticamente compases al abrir MusicXML — útil como
   referencia de comportamiento deseado).
4. **Reglas mínimas para el corpus objetivo de Cadenza** (monofónicas y piano simple):
   - Suma de duraciones = duración del compás (métrica).
   - Alturas dentro del rango de un instrumento/pentagrama razonable.
   - Armadura y alteraciones consistentes; mismas armaduras entre pentagramas (piano).
   - Figuras y silencios válidos; sin colisiones de tiempo en una misma voz.
   - Cierre de ligaduras y matices (en alcance inicial: básico).

## Dónde buscar más

- **Palabras clave:** "OMR error correction", "post-OMR validation", "symbolic music error detection",
  "music theory rules engine", "automatic score checking".
- **Venues:** ISMIR, IJDAR, MIR, Journal of New Music Research.
- **Estrategia:** la validación en OMR es un hueco conocido; la búsqueda debe confirmar que no haya
  trabajos recientes que ya resuelvan lo que Cadenza propone (para poder posicionar el aporte).
