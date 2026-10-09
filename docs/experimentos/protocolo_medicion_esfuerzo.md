# Protocolo Metodológico de Medición de Esfuerzo con Participantes (HITL)

**Proyecto:** Cadenza — Plataforma de Digitalización Asistida de Partituras  
**Documento:** Protocolo Experimental de Estudio de Usuarios HITL  
**Estado:** Formalizado y Aprobado  
**Versión:** 1.0  
**Fecha:** 2026-10-08  
**Relacionado:** Objetivo Específico 5, [ADR-0004](../adr/ADR-0004-persistencia-postgresql-jsonb.md), [ADR-0007](../adr/ADR-0007-edit-events-inmutables.md), [ADR-0009](../adr/ADR-0009-capa-de-aplicacion.md), [ADR-0012](../adr/ADR-0012-autenticacion-e-identidad.md), [ADR-0013](../adr/ADR-0013-revalidacion-y-versionado-de-hallazgos.md), [ARCHITECTURE.md](../ARCHITECTURE.md) §5.3, Deuda D38.

---

## 1. Fundamentación y Objetivos de la Investigación

### 1.1 Articulación con los Objetivos de la Tesis
El **Objetivo Específico 5** de la tesis establece:
> *«Evaluar experimentalmente el desempeño del flujo de digitalización asistida frente a una línea base OMR no asistida, utilizando conjuntos de datos de referencia y métricas de fidelidad de transcripción y esfuerzo de corrección humano, particularmente la tasa de error simbólico (SER), el tiempo de edición y las intervenciones manuales por compás.»*

Mientras que los experimentos 01 al 09 evaluaron de forma analítica y offline el rendimiento de los modelos OMR (HOMR, OEMER) y la capacidad de detección del validador de teoría musical, el presente protocolo formaliza el **estudio empírico con usuarios humanos (*Human-in-the-Loop*, HITL)** para validar la interacción real entre transcriptores y la plataforma Cadenza.

### 1.2 Pregunta de Investigación e Hipótesis
* **Pregunta de Investigación:** ¿En qué medida la asistencia interactiva de un motor de validación musical sintáctico reduce el esfuerzo temporal, operativo y la carga cognitiva percibida de los transcriptores humanos durante la corrección de partituras digitalizadas por OMR, en comparación con una línea base no asistida?
* **Hipótesis Principal ($H_1$):** El flujo asistido por validación reduce significativamente el tiempo promedio de corrección por compás ($T_{\text{asistido}} < T_{\text{no\_asistido}}$) y la tasa de intervenciones manuales por compás ($I_{\text{asistido}} < I_{\text{no\_asistido}}$), disminuyendo adicionalmente el índice global de carga cognitiva percibida (NASA-TLX).
* **Hipótesis Nula ($H_0$):** No existen diferencias estadísticamente significativas en el tiempo por compás, número de intervenciones ni carga cognitiva entre el flujo asistido y el no asistido.

---

## 2. Diseño Experimental

### 2.1 Esquema Intrasujeto (Within-Subjects)
Para maximizar la potencia estadística y neutralizar la alta varianza inherente a la pericia musical de los individuos, se adopta un **diseño intrasujeto balanceado** mediante técnica de **Cuadrado Latino ($2 \times 2$)**:
* Cada participante evalúa partituras en **ambas condiciones** (asistida y no asistida).
* Se contrabalancea el orden de presentación de las condiciones y las partituras para eliminar sesgos de aprendizaje secuencial (*carry-over effects*) y fatiga cognitiva.

### 2.2 Condiciones Experimentales
1. **Condición Asistida (`assisted`):**
   * El pipeline OMR transcribe la imagen y el `ValidationEngine` evalúa el catálogo de reglas musicales sintácticas (balance rítmico, coherencia métrica, alteraciones tonales).
   * La interfaz gráfica resalta visualmente los compases y eventos con discrepancias mediante anclas espaciales y semánticas, proveyendo mensajes de error explicables y sugerencias de corrección.
   * Las revalidaciones interactivas (`POST /sessions/{id}/validate`) actualizan los hallazgos tras cada corrección.
2. **Condición No Asistida (`unassisted`):**
   * El pipeline OMR genera la transcripción cruda, pero el validador **se desactiva completamente a nivel de sesión** (`findings = ()`).
   * La interfaz presenta el visor interactivo sin alertas, marcas de validación ni sugerencias.
   * El usuario debe inspeccionar secuencialmente cada compás comparándolo visualmente con la imagen original sin asistencia automatizada.

### 2.3 Banco de Partituras de Prueba (`test_score_id`)
Se establecen cuatro partituras de prueba calibradas en dificultad y complejidad estructural:
* **`TS-01` (Monofónica básica):** 4 compases en compás simple (4/4), tonalidad mayor básica, figuras regulares (negras, corcheas). Línea base de baja complejidad.
* **`TS-02` (Alteraciones y armaduras):** 8 compases con armadura de 3 alteraciones, accidentes cromáticos incidentales y síncopas moderadas.
* **`TS-03` (Rítmica compleja y ligaduras):** 8 compases con compás compuesto (6/8), tresillos, ligaduras de prolongación y silencios intercalados.
* **`TS-04` (Polifonía / Pianoform):** 12 compases distribuidos en sistema de dos pentagramas (clave de sol y fa), contrapunto a dos voces y acordes simultáneos.

### 2.4 Matriz de Contrabalanceo y Asignación de Bloques
Con una muestra mínima de $N=8$ transcriptores musicales:

| Participante | Bloque 1 | Bloque 2 | Bloque 3 | Bloque 4 |
|---|---|---|---|---|
| **P01** | TS-01 (`assisted`) | TS-02 (`unassisted`) | TS-03 (`assisted`) | TS-04 (`unassisted`) |
| **P02** | TS-01 (`unassisted`) | TS-02 (`assisted`) | TS-03 (`unassisted`) | TS-04 (`assisted`) |
| **P03** | TS-02 (`assisted`) | TS-01 (`unassisted`) | TS-04 (`assisted`) | TS-03 (`unassisted`) |
| **P04** | TS-02 (`unassisted`) | TS-01 (`assisted`) | TS-04 (`unassisted`) | TS-03 (`assisted`) |
| **P05** | TS-03 (`assisted`) | TS-04 (`unassisted`) | TS-01 (`assisted`) | TS-02 (`unassisted`) |
| **P06** | TS-03 (`unassisted`) | TS-04 (`assisted`) | TS-01 (`unassisted`) | TS-02 (`assisted`) |
| **P07** | TS-04 (`assisted`) | TS-03 (`unassisted`) | TS-02 (`assisted`) | TS-01 (`unassisted`) |
| **P08** | TS-04 (`unassisted`) | TS-03 (`assisted`) | TS-02 (`unassisted`) | TS-01 (`assisted`) |

---

## 3. Variables y Métricas de Medición

### 3.1 Variables Independientes
* **Condición experimental:** `assisted` vs `unassisted`.
* **Partitura de prueba:** `TS-01`, `TS-02`, `TS-03`, `TS-04`.
* **Secuencia de orden:** Bloque 1 a 4.

### 3.2 Variables Dependientes Cuantitativas (Telemetría Objetiva)
Registradas de forma inmutable en `sessions`, `edit_events` y `effort_metrics`:
1. **Duración total de corrección ($T_{\text{total}}$):** tiempo transcurrido en milisegundos (`duration_ms` / `duration_s`) desde la carga de la sesión hasta su finalización formal.
2. **Latencia a la primera edición ($T_{\text{first}}$):** tiempo de inspección exploratoria previa a la primera acción correctiva (`time_to_first_edit_ms`).
3. **Intervenciones manuales por compás ($I_{m}$):** conteo de operaciones de corrección (INSERT, UPDATE, DELETE) agrupadas por compás (`interventions`).
4. **Tiempo por compás ($T_{\text{compás}}$):** duración normalizada $T_{\text{total}} / N_{\text{compases}}$.
5. **Tasa de intervenciones ($I_{\text{tasa}}$):** intervenciones totales normalizadas $I_{\text{total}} / N_{\text{compases}}$.
6. **Eventos totales de edición ($E_{\text{count}}$):** total de correcciones en el log inmutable de `edit_events`.
7. **Fidelidad residual post-edición:** SER y OMR-NED comparados frente al Ground Truth al cierre de la sesión.

### 3.3 Variables Dependientes Subjetivas (Carga Cognitiva NASA-TLX)
Al concluir cada condición, el participante diligencia el cuestionario multidimensional **NASA Task Load Index (NASA-TLX)** valorado en escala de 0 a 100:
* **Demanda Mental:** ¿Cuánta actividad mental y perceptiva requirió la tarea?
* **Demanda Física:** ¿Cuánta actividad física o fatiga visual/motriz demandó?
* **Demanda Temporal:** ¿Cuánta presión temporal sintió por el ritmo de la tarea?
* **Rendimiento Percibido:** ¿Cuán exitoso se sintió corrigiendo los errores?
* **Esfuerzo:** ¿Cuán duro tuvo que trabajar para alcanzar su nivel de rendimiento?
* **Frustración:** ¿Cuán inseguro, desalentado o irritado se sintió durante la corrección?
* **Puntaje Global TLX:** promedio directo (*Raw TLX*) y ponderado por parejas.

---

## 4. Tratamiento Ético de Datos, Anonimato y Consentimiento Informado

### 4.1 Principios Éticos y Cumplimiento Normativo
El estudio se adhiere a los principios éticos internacionales de investigación con seres humanos en el ámbito de la interacción persona-computador (HCI) y ciencia de datos, derivados de la **Declaración de Helsinki** y la normativa de protección de datos personales.

### 4.2 Seudonimización Estricta (ADR-0012)
* **Ausencia de PII (*Personally Identifiable Information*):** El sistema **no solicita ni almacena nombres reales, correos electrónicos, números de identificación, direcciones IP ni datos biométricos**.
* **Identificadores Seudónimos:** Cada participante es dado de alta en la base de datos por el investigador mediante un código alfanumérico seudónimo (`P01`, `P02`, ..., `P08`) que actúa como `UserRecord.username` (ADR-0012).
* **Llave de Desvinculación Aislada:** La correspondencia entre el participante y su código seudónimo se conserva en un registro físico o digital encriptado fuera del repositorio y de los servidores de la plataforma, accesible únicamente por el investigador principal.
* **Control de Acceso:** Los transcriptores solo pueden consultar y operar sobre sus propias sesiones (`owner_id = current_user.id`). Solo el rol `investigador` puede consultar el agregado para la exportación de métricas.

### 4.3 Protocolo de Consentimiento Informado
Antes de iniciar la prueba, cada participante recibe un documento de información y firma el formulario de consentimiento con las siguientes garantías:
1. **Voluntariedad:** La participación es estrictamente voluntaria y no remunerada de forma coercitiva.
2. **Derecho de Retiro Incondicional:** El participante puede suspender la sesión o retirarse en cualquier momento sin necesidad de justificación ni consecuencia alguna.
3. **Uso Exclusivo Académico:** Los datos recolectados (tiempos, clics, ediciones y respuestas de cuestionarios) se usarán exclusivamente para el análisis estadístico de la tesis de maestría y publicaciones científicas derivadas.
4. **Publicación Anonimizada:** Cualquier gráfico o tabla estadística publicada contendrá únicamente resúmenes agregados o identificadores seudónimos disociados.

---

## 5. Procedimiento Operativo de la Sesión

1. **Recepción y Bienvenida (10 min):**
   * Entrega de la hoja informativa y firma del consentimiento informado.
   * Asignación del código seudónimo y credenciales temporales.
2. **Familiarización y Calentamiento (10 min):**
   * Breve recorrido por la interfaz web de Cadenza: herramientas de navegación, cursor, edición de notas, alteraciones y panel de hallazgos.
   * Ejercicio guiado de corrección sobre una partitura de prueba neutra no evaluada.
3. **Bloque Experimental 1 (15 min):**
   * Ejecución de las tareas correspondientes según la matriz de Cuadrado Latino.
   * Telemetría activa registrando eventos inmutables.
   * Diligenciamiento de la primera subescala NASA-TLX.
4. **Pausa de Descanso Cognitivo (5 min):**
   * Descanso visual obligatorio para mitigar fatiga acumulada.
5. **Bloque Experimental 2 (15 min):**
   * Ejecución de las tareas restantes en la condición alterna.
   * Diligenciamiento de la segunda subescala NASA-TLX.
6. **Cuestionario Final y Cierre (5 min):**
   * Breve encuesta de usabilidad cualitativa (facilidad de uso, claridad de los hallazgos).
   * Agradecimiento formal y cierre de sesión en la plataforma.

---

## 6. Pipeline de Exportación Tabular y Análisis Estadístico

### 6.1 Herramientas y Comandos de Extracción
Cadenza provee un módulo de exportación y CLI automatizado para extraer la telemetría del estudio a formatos tabulares limpios:
```bash
# Exportación directa desde la base de datos de producción / local:
uv run python ml/cli.py export-effort --db-url sqlite:///cadenza.db --output-dir results/

# O mediante ejecución del módulo de experimento:
uv run python -m ml.experiments.exp_10_effort_study --output-dir results/
```
Para auditoría en integración continua (CI) y validación de reproducibilidad sin requerir base de datos interactiva:
```bash
uv run python ml/cli.py export-effort --smoke --output-dir results/
```

### 6.2 Archivos de Datos Generados
1. **`results/effort_study_sessions.csv`:**
   * Detalle a nivel de sesión individual.
   * Columnas: `session_id`, `participant_id`, `condition`, `test_score_id`, `duration_ms`, `duration_s`, `time_to_first_edit_ms`, `total_measures`, `total_interventions`, `edits_count`, `findings_count`, `time_per_measure_s`, `interventions_per_measure`, `nasa_tlx_mental`, `nasa_tlx_effort`, `nasa_tlx_frustration`, `nasa_tlx_global`, `status`, `created_at`.
2. **`results/effort_study_by_measure.csv`:**
   * Datos longitudinales desagregados compás por compás para modelos lineales jerárquicos.
   * Columnas: `session_id`, `participant_id`, `condition`, `test_score_id`, `measure_number`, `interventions_count`.
3. **`results/effort_study_summary.json`:**
   * Resumen analítico con medias por condición y tasas relativas de reducción de esfuerzo:
     * Reducción porcentual de tiempo por compás: $\Delta T\% = (1 - T_{\text{asistido}} / T_{\text{no\_asistido}}) \times 100$.
     * Reducción porcentual de intervenciones: $\Delta I\% = (1 - I_{\text{asistido}} / I_{\text{no\_asistido}}) \times 100$.
     * Reducción porcentual de carga cognitiva global: $\Delta \text{TLX}\% = (1 - \text{TLX}_{\text{asistido}} / \text{TLX}_{\text{no\_asistido}}) \times 100$.
4. **`results/exp_10_run_info.json`:**
   * Metadatos de auditoría y trazabilidad científica (hash git, entorno, fecha y semilla).

### 6.3 Modelo Estadístico de Análisis
* **Prueba de Normalidad:** Test de Shapiro-Wilk sobre los deltas apareados $(\Delta T, \Delta I, \Delta \text{TLX})$.
* **Contraste de Hipótesis Principal:**
  * Si los datos cumplen normalidad: **Prueba t de Student para muestras relacionadas (pareadas)** bilateral ($\alpha = 0.05$).
  * Si no cumplen normalidad: **Prueba de rangos con signo de Wilcoxon** pareada.
* **Modelado Multivariado:** **Modelo Lineal Mixto (GLMM)** con efectos fijos para la `condición` y la `partitura`, y efectos aleatorios para el `participante`, evaluando interacciones entre complejidad musical y efectividad del validador.
