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

Mientras que los experimentos 01 al 06 evaluaron de forma analítica y offline el rendimiento de HOMR sobre PrIMuS y la capacidad de detección del validador de teoría musical, el presente protocolo formaliza el **estudio empírico con usuarios humanos (*Human-in-the-Loop*, HITL)** para validar la interacción real entre transcriptores y la plataforma Cadenza.

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
   * **Sugerencias aprendidas (#244, decisión del responsable del 2026-10-31):** la condición asistida incluye las sugerencias de la capa que aprende de las correcciones (ADR-0036), **solo las de alteración de confianza alta** (enmienda 19), y se prueban en el piloto (#251).
   * Las revalidaciones interactivas (`POST /sessions/{id}/validate`) actualizan los hallazgos tras cada corrección.
2. **Condición No Asistida (`unassisted`):**
   * El pipeline OMR genera la transcripción cruda, pero el validador **se desactiva completamente a nivel de sesión** (`findings = ()`).
   * La interfaz presenta el visor interactivo sin alertas, marcas de validación ni sugerencias. Tampoco ofrece «Revalidar» ni dice nada del validador, y al finalizar no se valida (ADR-0040 §13, ADR-0043).
   * El usuario debe inspeccionar secuencialmente cada compás comparándolo visualmente con la imagen original sin asistencia automatizada.

### 2.3 Banco de Partituras de Prueba (`test_score_id`)
Se establecen cuatro partituras de prueba calibradas en dificultad y complejidad estructural:
* **`TS-01` (Monofónica básica):** 4 compases en compás simple (4/4), tonalidad mayor básica, figuras regulares (negras, corcheas). Línea base de baja complejidad.
* **`TS-02` (Alteraciones y armaduras):** 8 compases con armadura de 3 alteraciones, accidentes cromáticos incidentales y síncopas moderadas.
* **`TS-03` (Rítmica compleja y ligaduras):** 8 compases con compás compuesto (6/8), tresillos, ligaduras de prolongación y silencios intercalados.
* **`TS-04` (Voz y piano):** voz superior con acompañamiento de piano en dos pentagramas (clave de sol y fa), con acordes simultáneos. Decidido por el responsable el 2026-11-01 (#244), según el alcance del plan de cierre; depende de #239.

**El banco real (#247, aprobado por el responsable el 2026-11-01).** Cada partitura se transcribe con su `test_score_id` (`TS-01` a `TS-04`, y `calentamiento` para la del §5). Las imágenes y las verdades no se versionan: `scripts/build_study_bank.py` las regenera en `banco_estudio/` desde las fuentes de `data/` y comprueba los sha256 de `docs/experimentos/banco_de_partituras.json`, el manifiesto con el origen, la licencia, la página, el recorte y las erratas de cada una ([ADR-0057](../adr/ADR-0057-banco-de-partituras-del-estudio.md)).

| `test_score_id` | Partitura | Imagen | Verdad | Contenido |
|---|---|---|---|---|
| `calentamiento` | Íncipit de RISM en PrIMuS `190009364-1_1_1` | Su PNG: un render de Verovio, no un escaneo | Su MEI con la altura del `.semantic` | Melodía en fa mayor, compás C, anacrusa y 2 compases |
| `TS-01` | Íncipit de RISM en PrIMuS `000106106-1_1_1` | Su PNG: un render de Verovio | Ídem | Melodía en sol mayor, compás C, 4 compases de negras y corcheas |
| `TS-02` | Schubert, *Winterreise* n.º 16, *Letzte Hoffnung*, cc. 6-13 | P. 57 del PDF (53 impresa), sistemas 2 y 3, a 300 ppp | OpenScore `lc5007180` | Voz y piano, tres bemoles, 3/4, accidentes, acordes, dos voces y cambios de clave a mitad de compás |
| `TS-03` | *Winterreise* n.º 11, *Frühlingstraum*, cc. 14-21 | P. 40 del PDF (36 impresa), sistemas 4 y 5 | OpenScore `lc5023603`, con una errata (ADR-0057 §5) | Voz y piano, tres sostenidos, 6/8, tresillos de semicorcheas, ligaduras de prolongación, silencios y acordes |
| `TS-04` | *Winterreise* n.º 21, *Das Wirthshaus*, cc. 8-13 | P. 72 del PDF (68 impresa), sistemas 3 y 4 | OpenScore `lc5013945` | Voz y piano, un bemol, compás C (sin imprimir en el recorte), 6 compases: acordes en las dos manos, varias voces, una nota de adorno y un silencio de redonda en la voz |

- **Licencias:** los íncipits, CC BY (RISM); el PDF de IMSLP #60822 (*Schuberts Werke*, Serie XX, Band 9, Breitkopf & Härtel, 1895), dominio público; las verdades de OpenScore Lieder, CC0. Los compases son ordinales (la anacrusa es el 1; OpenScore la numera 0).
- **Las verdades se comprobaron a mano** contra la imagen, compás a compás. TS-02 y TS-03 no imprimen la indicación de compás (está en el sistema 1): su verdad lleva el 3/4 y el 6/8, que la persona pone con la barra (#241).
- **D62:** ninguna partitura tropieza con él. En la vista se elige nota a nota en las cinco, a 1440 y a 390 px, también tras poner el compás; el único silencio de compás entero es el de la voz de TS-04 (c. 3), en 4/4, y se elige como los demás.

**Lo que HOMR lee y lo que la barra corrige** (tercera revisión exploratoria, del 2026-11-03, sobre `dev` 6ba625f, con #237, #239, #317, #318, #325 y #326: el sistema del congelado, HOMR 0.7.0 en CPU como en producción y la API con la configuración por defecto. Cada partitura se transcribió por la API local con su `test_score_id`, en la condición asistida, y se corrigió en la vista con Playwright sin ventana —Chromium, `1440×1500`, no el navegador integrado—, eligiendo cada nota en `useSelectionStore` y pulsando los botones de la barra, sin usar el teclado ni el puntero sobre la partitura; los scripts aplicaron directamente las ediciones necesarias —`TS-01` quedó corregida antes con una primera pasada del script en el scratchpad— y lo corregido se comparó con la verdad materializando el log, por lo que se ve. Las cifras son **exploratorias** —salen de los scripts de la revisión, no de `ml/experiments`— y no son un resultado de la tesis. Las tablas de la primera y de la segunda revisión quedan en el historial de este archivo (4620c9b y a28707f); lo que cambió entre las tres, en [ADR-0057 §Segunda revisión](../adr/ADR-0057-banco-de-partituras-del-estudio.md#segunda-revisión-2026-11-02) y [§Tercera revisión](../adr/ADR-0057-banco-de-partituras-del-estudio.md#tercera-revisión-2026-11-03)):

| `test_score_id` | Errores de HOMR | Ediciones desde la vista | Queda sin corregir | Posibles errores falsos |
|---|---|---|---|---|
| `calentamiento` | Ninguno; lee también la C (#237) | 0 | Nada | Ninguno |
| `TS-01` | Lee el C como 2/4 y divide entre dos las 12 figuras de los cc. 1-3 (la etapa del compás no lo arregla: la suma más repetida es la de 2/4); las alturas, bien | 13: la C y doce figuras | Nada: el `ScoreIR` queda igual que la verdad | Ninguno: los dos de duración (cc. 1 y 4) son ciertos para el 2/4 y se van al corregir las figuras, poner la C y revalidar |
| `TS-02` | Sin compás; el Si♭3 que falta en el acorde de la mano izquierda (c. 6); en la mano derecha del c. 3, la corchea Mi♭5 en el acorde de la otra voz y sin su ligadura. La voz, sin errores | 11: 3/4 en todas las partes (una, #326), el Si♭3 (cinco) y la ligadura (cinco: la corchea se escribe en la voz de la negra desde su hueco, #317) | Nada de lo que se ve | Ninguno (tres en la primera revisión, #318) |
| `TS-03` | Sin compás; la voz, sin errores. Con #325 (el piano leído emparejado y solo, y combinado mano a mano), la mano izquierda recupera la vuelta a la clave de fa del c. 7 y coincide con la verdad en los cc. 1, 3, 4, 5, 6, 7 y 8, sin huecos ni notas desplazadas; en ella solo faltan las tres ligaduras del acorde La2–Mi3–La3 del c. 2. En la mano derecha quedan la voz de abajo del c. 2 omitida (HOMR funde las dos voces en un Do♯4 negra con puntillo sin hueco) y los tresillos de semicorcheas sin marcar en los cc. 4 y 8 (lo que falta y sobra frente a la verdad baja de 48 / 45 a 26 / 25) | 8 necesarias (aplicadas por el script; 79 necesarias en la segunda revisión, de las que desaparecen 71: compás 1, huecos 2, c. 6 11, clave 1 y alturas y hueco de los cc. 7-8 56): 6/8 en todas las partes con «Cambiar compás» (una, #326), el Do♯4 del c. 2 de la mano derecha a corchea con «Corchea» y «Puntillo» (dos), los dos tresillos de los cc. 4 y 8 con «Tresillo en tres figuras desde la elegida» («Tres», dos) y las tres ligaduras del acorde del c. 2 de la mano izquierda con «Ligar con la siguiente» («Ligar», tres) | La voz de abajo del c. 2 de la mano derecha (Do♯4 con puntillo ligado): HOMR da una voz sin hueco y la barra no crea voces. Faltan 2 eventos y sobra 1 | Ninguno: tras poner el 6/8 con «Cambiar compás» y pulsar «Revalidar» (#329), 3 avisos de `measure.balance` en los compases que no cuadran (mano derecha, cc. 2, 4 y 8), todos ciertos |
| `TS-04` | Sin compás; en la mano derecha del c. 6, un Do4 donde hay un silencio de corchea. Lee bien los acordes y las varias voces | 9: la C en todas las partes (una, #326), el Do4 (una) y el silencio (siete) | Nada de lo que se ve | Ninguno (siete en la primera revisión, #318) |

En TS-02, TS-03 y TS-04 la voz va arriba, en su parte, y el piano debajo, con sus dos pentagramas y la llave (#239). En la tercera revisión se comprobó que el mapa de selección quedó listo (`data-status="ready"`) en las cinco, y a 390 px no hay desbordamiento con un puntero táctil (`pointer: coarse`), mientras que en escritorio (`pointer: fine`) la leyenda `.editor__keys` llega a 445 px ([#331](https://github.com/sebdavid3/Cadenza/issues/331)).

**Riesgos para el estudio** (tras la tercera revisión; lo resuelto por #239, #317, #318, #325 y #326 se describe en ADR-0057):
- **TS-03 baja de 79 a 8 ediciones necesarias** gracias a #325 y #326, en el mismo rango que TS-01 (13), TS-02 (11) y TS-04 (9). Solo queda sin poder escribirse desde la barra la segunda voz del c. 2 de la mano derecha (Do♯4 con puntillo ligado, porque HOMR da una sola voz sin hueco y la barra no crea voces: faltan 2 eventos y sobra 1, SER exploratorio 0,125).
- **TS-04 se recortó a los cc. 8-13.** Con la página entera (cc. 1-13), HOMR mezcla los pentagramas del sistema 2 y la vista no puede corregirlo (primera revisión). Son 6 compases, no 12.
- **El compás** no se lee en TS-02, TS-03 y TS-04 (el recorte no lo imprime y la etapa de #237 solo corrige lo que HOMR leyó) y en TS-01 se lee 2/4. Con #326 y #329 una sola acción lo pone en todos los compases de todas las partes, y «Revalidar» comprueba el balance de todos ellos (en TS-03 señala los 3 avisos ciertos de `measure.balance` en los cc. 2, 4 y 8 de la mano derecha).
- **Añadir un silencio al final de una voz** cuesta siete ediciones (la barra solo inserta antes del evento elegido): TS-04, c. 6 (en TS-03, c. 6 ya no hace falta tras #325).
- **Un cambio de clave a mitad de compás** (mano izquierda de TS-02 y TS-03) no se puede poner desde la vista: las alturas están bien, pero esas notas se dibujan distintas de la imagen.
- **El calentamiento no tiene nada que corregir**: el ejercicio guiado (§5) necesita otra tarea o tocar algo a propósito.
- **La fidelidad residual (#250)**: la verdad y la sesión tienen ya los pentagramas en el mismo orden, pero el número de voz y el orden de las notas de un acorde cambian el SER aunque lo que se ve sea igual (0,162 en TS-02 y 0,369 en TS-04, corregidas sin nada que falte ni sobre). #250 debe normalizarlos antes de medir.

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
1. **Duración total de corrección ($T_{\text{total}}$):** tiempo **con la página visible y con actividad**, en milisegundos (`duration_ms` / `duration_s`), desde la primera carga de la sesión hasta su finalización formal (definición en el §3.4).
2. **Latencia a la primera edición ($T_{\text{first}}$):** tiempo de inspección exploratoria previa a la primera acción correctiva (`time_to_first_edit_ms`).
3. **Intervenciones manuales por compás ($I_{m}$):** conteo de las ediciones guardadas agrupadas por compás (`interventions`), según el §3.4.
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

**Recogida (#244, decisión del responsable del 2026-11-01):** el cuestionario se rellena fuera de la web (en papel o en un formulario en línea) y se pasa a un CSV con una fila por participante y bloque, que `exp_10` une por esas dos columnas (#250). Sin dato, la celda queda vacía, nunca a 0.

### 3.4 Definiciones operativas (#244)
Decididas por el responsable el 2026-11-01 para que #188 registre el esfuerzo sin ambigüedad:
* **Duración: solo el tiempo con la pantalla delante.** Se suman los tramos en que la página de la sesión está visible (`document.visibilityState`) y hay actividad. Se descuenta lo que la pestaña estuvo oculta y cada pausa sin actividad (ni teclado ni ratón ni toque) más larga que el umbral, de la que solo cuenta el umbral. **Umbral: 2 minutos** (confirmado por el responsable el 2026-11-01). Las recargas de la página no cortan la medición: se acumula sobre el mismo registro. Una partitura que no se finaliza no entra en el análisis.
* **Intervenciones: cada acción cuenta.** Cada edición guardada es una intervención en el compás de su ancla, también deshacer y rehacer, que son ediciones que compensan otra (ADR-0034), y las marcas, el compás y los tresillos (ADR-0039 y ADR-0044, contadas por su clase). Descartar y restaurar un posible error, y aplicar o rechazar una sugerencia, se cuentan aparte.
* **Reabrir: un solo registro por sesión.** Si se reabre una sesión finalizada y se vuelve a finalizar, el registro acumula todo hasta la última finalización.
* **Condición no asistida:** no se muestra nada del validador ni de la capa de sugerencias (ADR-0040 §13).

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
   * Ejercicio guiado de corrección sobre una partitura de prueba neutra no evaluada (`calentamiento`, §2.3).
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
uv run python -m ml.experiments.exp_10_effort_study --db-url sqlite:///cadenza.db --output-dir results/
```
Sin `--db-url`, o con una base sin sesiones del estudio, la exportación falla: no rellena con
datos sintéticos ([#271](https://github.com/sebdavid3/Cadenza/issues/271)). Para probar la
exportación sin base de datos, `--smoke` genera datos sintéticos, marcados con
`"simulated": true` en el resumen y en el `run_info`, y exige una carpeta fuera de `results/`:
```bash
uv run python ml/cli.py export-effort --smoke --output-dir <carpeta temporal>
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
