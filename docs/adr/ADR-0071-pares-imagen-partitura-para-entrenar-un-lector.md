# ADR-0071: Los pares imagen–partitura para entrenar un lector

- **Estado:** Aceptado
- **Fecha:** 2026-11-19
- **Decisores:** Responsable del proyecto (pidió el 2026-11-09, en #400, que los datos de la plataforma sirvan para entrenar un modelo de transcripción mejor, eligió el 2026-11-19 el MusicXML por tira entre las tres opciones y decidió el mismo día que las cuentas del registro con el permiso vigente entren por defecto, #422) y Equipo de Desarrollo
- **Relacionado:** [INV-0001](../investigaciones/INV-0001-salidas-internas-homr-bbox-y-confianza.md), [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md), [ADR-0065](ADR-0065-permiso-de-uso-de-los-datos-al-registrarse.md), [ADR-0067](ADR-0067-captura-de-homr-y-recortes-de-los-pentagramas.md), [ADR-0068](ADR-0068-tablas-y-recortes-en-una-sola-exportacion.md), [#103](https://github.com/sebdavid3/Cadenza/issues/103), [#255](https://github.com/sebdavid3/Cadenza/issues/255), [#420](https://github.com/sebdavid3/Cadenza/issues/420), [#422](https://github.com/sebdavid3/Cadenza/issues/422)

---

## Contexto

`ml export-staves` (ADR-0067) ya recorta de cada foto la tira de cada pentagrama (o del gran pentagrama del piano) y la empareja con sus compases leídos y corregidos. Pero la transcripción de la tira va en un texto propio de Cadenza (`c1: F4:1 …`, `strip_sequence`), que ningún lector sabe entrenar, y el MusicXML que escribe es el de la página entera. Falta el par que pide un entrenamiento: **la imagen de una tira y su partitura en un formato estándar**, con la partición fija y una ficha que diga de dónde salen los datos y con qué permiso. Reentrenar sigue fuera de la entrega (D14, #103): esto solo deja los pares listos.

### Qué pide el entrenamiento de HOMR

Revisado el 2026-11-19 en `github.com/liebharc/homr` (la etiqueta `v0.7.0`, la versión de producción, y la rama principal):

- El transformador se entrena con un **índice de líneas `imagen,etiqueta`**: la imagen de un pentagrama (o de un gran pentagrama) y un archivo `.tokens` en el **formato propio de HOMR**, un símbolo por línea con sus ramas (ritmo, altura, alteración, articulación, ligadura y posición `upper`/`lower` en el gran pentagrama). Sus duraciones se escriben como en **kern, pero el archivo no es **kern.
- Ese formato no se escribe a mano: HOMR lo **genera** desde tres fuentes, cada una con su conversor (`training/omr_datasets`):
  - **OpenScore Lieder** (y en la rama principal, **PDMX**): **MusicXML**, que MuseScore dibuja y se corta por pentagrama; `music_xml_parser` lo pasa a `.tokens`.
  - **GrandStaff**: **kern (`**bekern`), con `humdrum_kern_parser`.
  - **Camera-PrIMuS** (solo hasta la 0.7.x): la codificación **semantic**, con `primus_semantic_parser`. La rama principal la quitó el 2026-11-09 (6e00e38, «Remove PrIMuS leftovers and unused code») y el 2026-11-13 duplicó los datos de PDMX para suplir los unos 80 000 de PrIMuS (2ae866d): hoy HOMR ya no lee semantic.
- El MusicXML es, por tanto, la entrada que HOMR mantiene, y la que más le sirve: un MusicXML por tira se pasa a `.tokens` con su propio conversor, sin dibujar nada.

### Qué usa PrIMuS

PrIMuS son 87 678 *incipits* de RISM dibujados con Verovio: imágenes sintéticas, no fotos (Camera-PrIMuS les añade distorsiones que imitan una cámara). Cada uno trae su imagen y su partitura en cinco codificaciones: MEI, Plaine & Easie, MIDI, **agnostic** (símbolos gráficos con su posición en el pentagrama) y **semantic** (`clef-G2 keySignature-EbM timeSignature-3/4 note-Bb5_quarter … barline`). Las dos últimas son **monofónicas, de un pentagrama y una voz**: no tienen acordes, ni varias voces, ni gran pentagrama, ni ligaduras de expresión ni dinámicas. Cadenza ya las lee para `exp_12` (#255), donde la verdad es la altura que suena del `.semantic`.

### Las tres opciones

| | MusicXML por tira | semantic de PrIMuS | **kern |
|---|---|---|---|
| **Qué cabe** | Todo el `ScoreIR`: acordes, voces, gran pentagrama, ligaduras, notas de adorno, articulaciones, dinámicas | Una voz de un pentagrama: ni acordes ni piano ni voces | Polifonía y gran pentagrama (columnas), ligaduras y adornos |
| **Quién lo lee** | HOMR (Lieder y PDMX, también en la rama principal), music21, MuseScore, Verovio | HOMR hasta la 0.7.x; ya no en la rama principal. Lectores de PrIMuS y sus derivados | HOMR (GrandStaff), music21, Verovio, Humdrum |
| **Coste en Cadenza** | Ya existe: `score_ir_to_musicxml` y la importación inversa, que permite comprobar la ida y la vuelta | Un escritor nuevo, y las tiras de piano, con acordes o con varias voces quedarían fuera o perderían información | Un escritor nuevo (music21 lee **kern pero no lo escribe), con columnas, voces partidas y ligaduras: más código y más riesgo de que la verdad salga mal |
| **Pegas** | Verboso; hay que pasarlo a `.tokens` (HOMR tiene el conversor) | Pierde lo que más corrige la gente en un piano | Formato menos conocido; HOMR lo lee solo como `**bekern` de GrandStaff |

En las pruebas con público hay páginas de piano y de voz y piano (ADR-0060), con acordes y dos voces por pentagrama: la codificación semantic dejaría fuera justo esas tiras.

## Decisión

1. **El formato: MusicXML por tira** (elección del responsable del 2026-11-19). Cada par lleva el PNG de la tira y **dos MusicXML de esa tira**: el que leyó HOMR (el estado 0 de la sesión) y el corregido (el estado final). Ni `.tokens` de HOMR ni semantic ni **kern: el que entrene (#103) los convierte con el conversor de su lector, y el MusicXML se puede volver a leer sin pérdida para cualquier otro.
2. **El MusicXML de una tira** (`cadenza.learning.staff_strips.strip_score`): una partitura con la parte de la tira y solo sus pentagramas (uno, o los dos de un gran pentagrama) y sus compases, con sus números de la página. Su primer compás lleva la clave, la armadura y el compás que rigen allí aunque la página no los repita (la clave y la armadura se dibujan al empezar cada sistema; el compás, no). Lo escribe `score_ir_to_musicxml` con `stable=True`, una opción nueva que quita la fecha de codificación y numera las partes en orden (P1, P2…) en vez de los identificadores al azar de music21, para que la misma sesión dé los mismos bytes cualquier día; sin ella, la exportación de la API no cambia. Como desde la vista no se insertan ni se borran compases (ADR-0067 §5), la misma tira vale para la lectura y para la corrección.
3. **Un subcomando nuevo, `ml export-pairs`**, y no una opción de `export-staves`: filtra de otra forma (solo sesiones verificadas, con la partición obligatoria) y escribe en otra disposición. Reutiliza `plan_strips`, la foto enderezada (`open_photo`) y las guardas de la salida de `export-staves`.
4. **Qué sesiones entran:**
   - solo las **finalizadas**: la corrección de una sesión abierta no es una verdad que alguien haya dado por buena;
   - solo las **verificadas**: las ediciones derivadas de la lectura al estado final lo reproducen (`materialize(leído, derive_edit_events(leído, final)) == final`, la comprobación de `session_records`, que pasa a `cadenza.learning.suggestions.correction_verified` para que las dos la compartan). Desde la vista ninguna corrección cambia el número de compases, que es lo que la alineación no explica, así que casi todas lo estarán;
   - de las cuentas del registro, **por defecto las que tienen el permiso de uso de los datos vigente** (`has_current_data_consent`, ADR-0065; decisión del responsable del 2026-11-19, la de [#422](https://github.com/sebdavid3/Cadenza/issues/422)), y ninguna con `--exclude-self-registered`. Las que no lo tienen (nunca lo dieron, lo retiraron o lo dieron para otro texto) **quedan siempre fuera**, también con opciones, y `run_info.json` solo cuenta cuántas sesiones se quedaron fuera por eso (ni su identificador; lo mismo con las que deja fuera la opción). Una sesión cuya cuenta no está queda fuera. Las cuentas que no vienen del registro (las del equipo, anteriores a ADR-0070, que quitó las del estudio) entran como en las otras exportaciones;
   - quedan fuera, con su motivo, las que no tienen captura, imagen o página de origen, y las que `plan_strips` rechaza.
5. **La partición fija por obra de #255:** `assign_split(obra, seed, test_fraction)`, con `--split-seed` obligatoria y `--test-fraction` (0,2). La obra es la partitura de prueba o el sha256 de la foto, como en `page_of`, pero **las sesiones que comparten una u otra son la misma obra, también encadenadas** (`cadenza.learning.suggestions.shared_works`): las imágenes del banco son idénticas byte a byte, y una página del banco subida sin `test_score_id` tendría `image:<sha256>` y podría caer en la otra partición que su partitura de prueba (lo encontró la revisión independiente). La obra de un grupo es su partitura de prueba menor o, sin ninguna, su foto menor; sin nada compartido, la de `page_of`. Todas las tiras de una obra caen del mismo lado, y ninguna foto ni ninguna tira está en las dos particiones.
6. **La salida:**
   - `train/<sesión>/` y `test/<sesión>/`, con `s<sistema>_<parte>-<pentagrama>.png`, `….homr.musicxml` y `….musicxml` (el corregido) por tira;
   - `pares.csv`: una fila por par, con su partición, su obra, la sesión, el sistema, los pentagramas, los compases, la versión de HOMR, las rutas de sus tres archivos con su sha256, el tamaño de la imagen, la foto de origen y si la corrección cambió la tira (`corregido`: los dos MusicXML difieren, así que cuenta también la clave, la armadura, el compás y las marcas, que la secuencia de `pentagramas.csv` no ve) (columnas en [`pares_imagen_partitura.md`](../experimentos/pares_imagen_partitura.md));
   - `run_info.json`: el commit, la fecha, los filtros, el permiso (`consent`: su versión, las sesiones sin el permiso vigente y las que deja fuera `--exclude-self-registered`), las sesiones exportadas y las que quedan fuera con su motivo, los recuentos por partición, las versiones de HOMR, el sha256 de `pares.csv` y de la ficha y `"simulated": false`;
   - `README.md`: la ficha del dataset, escrita con las cifras de esa exportación: origen, licencias, permiso, partición y limitaciones.
   - Como en `export-staves`, ha de estar vacía y no puede caer en `results/` ni en `data/` del repositorio.

## Consecuencias

### Positivas
- Un lector se puede reentrenar con los datos de la plataforma sin tocarla: HOMR pasa MusicXML a sus `.tokens` con su conversor, como hace con Lieder y PDMX, y cualquier otro lector lee MusicXML. No se ha pasado aquí ningún par por ese conversor, que es código de entrenamiento fuera del paquete de HOMR: lo hará #103.
- La lectura y la corrección de cada tira salen del mismo exportador: sus diferencias son solo las correcciones.
- Las tiras de piano, con acordes y con varias voces, entran enteras.
- La misma base da los mismos `pares.csv` y los mismos archivos: sus sha256 sirven para comprobar una copia.
- Probado sobre SQLite temporal (`packages/learning/tests/test_export_pairs.py`): el permiso (vigente, del texto anterior, nunca dado o retirado, cuentas anteriores al registro, y la opción), la partición sin fugas (también una página del banco subida sin su partitura de prueba), las sesiones sin captura, sin finalizar y sin verificar, un cambio de clave que marca las dos tiras en que rige, y el contenido de los pares de un pentagrama y de un gran pentagrama, leído de vuelta con la importación de Cadenza.

### Negativas / Riesgos
- **Sin cajas por nota:** cada par es una tira por sistema, sin la posición de cada símbolo (HOMR no la da, INV-0001). Basta para un lector de secuencias como el de HOMR, no para uno de detección.
- **El primer compás de un sistema puede salir corrido** cuando HOMR no detectó la barra que cierra un pentagrama (ADR-0067, riesgos): esa tira y la siguiente comparten un compás de más o de menos.
- **Dos fotos distintas de la misma página impresa**, sin partitura de prueba que las una, tienen distinto sha256: son dos obras y pueden caer en particiones distintas. Y una obra puede cambiar de lado si una sesión nueva la une a otra.
- **La partición de las tablas y de la capa de sugerencias** (`session_records`) sigue con `page_of`, sin unir las sesiones que comparten foto: cambiarla movería el corpus de #255 y sus mediciones, y no se hace aquí.
- **El compás se escribe aunque la tira no lo dibuje:** quien convierta a los `.tokens` de HOMR ha de decidir si lo quita en las tiras que no empiezan la obra.
- **Hasta que se haga #422**, `export-tables`, `export-staves` y `build-dataset` siguen dejando fuera por defecto las cuentas del registro (ADR-0067 §4, ADR-0068): esta exportación nace con el criterio nuevo, y #422 enmienda los demás con el mismo filtro y debería usar el mismo nombre de opción, `--exclude-self-registered`.
- **Los datos son de personas:** la salida tiene sus fotos y se trata como tal (ADR-0065): no se publica, se usa solo dentro del proyecto, y una exportación vieja se borra cuando alguien retira su permiso.
- PrIMuS no entra: sus imágenes son dibujos de Verovio, no fotos, y su partitura ya es semantic.

## Alternativas consideradas
1. **La codificación semantic de PrIMuS.** Monofónica: perdería el piano, los acordes y las voces, y la rama principal de HOMR ya no la lee.
2. **kern.** Cabría todo, y HOMR lo lee para GrandStaff, pero Cadenza tendría que escribir y mantener un conversor nuevo, y un error suyo estropearía la verdad.
3. **Los `.tokens` de HOMR.** Atarían los datos a una versión de un lector cuyo vocabulario cambia, y su conversor es código AGPL de entrenamiento que no viene en el paquete.
4. **Una opción de `export-staves`.** Mezclaría dos filtros y dos disposiciones en un comando.
