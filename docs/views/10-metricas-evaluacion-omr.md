# Vista 10: Métricas del Sistema y Evaluación OMR

- **Ruta Frontend:** `/admin/metrics`
- **Acceso:** Restringido (exclusivo para usuarios con rol `investigador`)
- **Modo Impeccable:** `Read` / `Operate`

---

## 1. Propósito y Audiencia
Es el **tablero de experimentación científica de la tesis**. Presenta los resultados empíricos reales de los experimentos de evaluación del OMR, tiempos de inferencia en GPU vs. CPU, precisión del validador de reglas, reducción de fatiga editorial humana y comparativas entre motores (`HOMR` vs `oemer`).

**Audiencia:** Investigadores, directores de tesis y evaluadores académicos.

---

## 2. Contrato de API y Fuentes de Datos
- `GET /sessions/effort`: Consulta agregada de métricas de esfuerzo de todas las sesiones cerradas.
- Datos de experimentos de la tesis versionados en `results/` y documentados en [`docs/PROJECT_STATE.md`](../../docs/PROJECT_STATE.md):
  - `exp_01_effort.py`: Reducción del esfuerzo de inspección gracias al validador sintáctico.
  - `exp_03_omr_quality.py`: Calidad de HOMR (OMR-NED y SER) frente a la verdad de referencia.
  - `exp_06_validation_metrics.py`: Precisión y recall del validador de reglas.
  - `exp_11_latency_benchmark.py`: Latencia de inferencia de HOMR en GPU vs CPU (arranque en frío: 3.3s–11.2s; inferencia en caliente: 0.69s–0.91s por fragmento).

---

## 3. Anatomía Visual y Layout

```
+--------------------------------------------------------------------------------------------------+
| [Logo] cadenza  TELEMETRÍA CIENTÍFICA & EVALUACIÓN OMR                      admin (investigador) |
+--------------------------------------------------------------------------------------------------+
| RESUMEN DE HIPÓTESIS Y RESULTADOS EMPÍRICOS DE LA TESIS                                          |
|                                                                                                  |
| [ Reducción de Esfuerzo ]   [ Precisión Validador ]   [ Latencia HOMR GPU ]   [ Tasa Corrección] |
|        -42.8%                     91.4%                     0.78s / página          0.62 edits/c |
+--------------------------------------------------------------------------------------------------+
| COMPARATIVAS Y TABLAS DE EXPERIMENTOS:                                                           |
|                                                                                                  |
| LATENCIA DE INFERENCIA (exp_11):         | PRECISIÓN DEL VALIDADOR DE REGLAS (exp_06):           |
| ──────────────────────────────────────── | ───────────────────────────────────────────────────── |
| Modalidad        Frío       Caliente     | Regla Sintáctica        Precisión   Recall   Falsos + |
| HOMR (GPU CUDA)  3.30s      0.78s        | Suma de compás (métrica) 96.2%       94.1%    3.8%    |
| HOMR (CPU x86)   11.29s     4.16s        | Armadura / Alteración   88.5%       82.0%    11.5%   |
| oemer (CPU base) 28.40s     18.20s       | Choque de voces         92.0%       89.4%    8.0%    |
|                                          |                                                       |
| [ Ver script exp_11 ]                    | [ Ver script exp_06 ]                                 |
+--------------------------------------------------------------------------------------------------+
| ESTUDIO DE ESFUERZO COGNITIVO HUMANO (exp_01 / exp_10):                                         |
|                                                                                                  |
| Condición Experimental      Tiempo Medio Sesión   Latencia 1ª Edición   Compases Corregidos      |
| ──────────────────────────────────────────────────────────────────────────────────────────────── |
| Grupo A (Con Validador HITL) 04m 12s               12.4s                 98.2% exactos           |
| Grupo B (Sin Validador)     07m 45s               48.6s                 86.5% exactos           |
| Delta de Mejora             -45.8% tiempo         -74.4% detección      +11.7% calidad final    |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Componentes y Funcionalidades

1. **KPI Cards Científicas:**
   - 4 tarjetas destacadas con cifras tabulares y deltas porcentuales claros.
   - Cada métrica cita explícitamente el experimento del cual proviene (ej. *"Fuente: exp_11_latency_benchmark.py"*).
2. **Tablas de Comparación de Rendimiento:**
   - Filas densas de 36px con números en tipografía monoespaciada alineados a la derecha.
   - Comparativa de hardware: HOMR en GPU NVIDIA (CUDA 12) frente a ejecución en CPU.
3. **Desglose de Reglas del Validador:**
   - Tabla que desglosa el rendimiento regla por regla: qué reglas musicales tienen mayor precisión y cuáles generan más falsos positivos (hallazgos descartados por transcriptores).
4. **Exportador de Datos de Investigación:**
   - Botón secundario `Exportar Datos de Tesis (CSV / JSON)` para alimentar scripts en LaTeX o análisis estadístico externo.

---

## 5. Estados de la Pantalla
- **Normal:** Visualización de métricas respaldadas empíricamente.
- **Sin Ejecutar / Pendiente:** Si un experimento aún no se ha medido (como la línea base de oemer en #100), la celda muestra explícitamente `Pendiente de ejecución (#100)` con un badge ámbar, cumpliendo a rajatabla **CLAUDE.md §8** (prohibido inventar cifras).

---

## 6. Atajos de Teclado
- <kbd>Ctrl+E</kbd>: Descarga el CSV con la telemetría agregada.
- <kbd>Esc</kbd>: Regresa al Dashboard.

---

## 7. Anti-patrones Prohibidos en esta Vista
- **Prohibido:** Gráficos cosméticos sin escala ni valores numéricos legibles; los datos de investigación deben ser tabulados y auditables.
- **Prohibido:** Falsos benchmarks de competidores comerciales sin medición real documentada.
