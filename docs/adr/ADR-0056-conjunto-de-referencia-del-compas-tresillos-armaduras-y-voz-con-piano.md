# ADR-0056: Conjunto de referencia del compás, los tresillos, las armaduras y la voz con piano

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0018, ADR-0031, ADR-0032 y ADR-0044, CLAUDE.md §8 y §9)
- **Relacionado:** [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md), [ADR-0044](ADR-0044-compas-con-su-simbolo-y-tresillos-como-edicion.md), [INV-0002](../investigaciones/INV-0002-audiveris-frente-a-homr.md), [#234](https://github.com/sebdavid3/Cadenza/issues/234), [#236](https://github.com/sebdavid3/Cadenza/issues/236), [#237](https://github.com/sebdavid3/Cadenza/issues/237), [#238](https://github.com/sebdavid3/Cadenza/issues/238), [#239](https://github.com/sebdavid3/Cadenza/issues/239), [#247](https://github.com/sebdavid3/Cadenza/issues/247)

---

## Contexto

#237 (el compás por tramos, C y ¢, y los tresillos implícitos), #238 (los cambios de armadura) y #239 (la voz superior y el piano) tienen que medir antes y después (CLAUDE.md §8), y lo que había no bastaba:

- **PrIMuS** sirve para el numerador del compás y para C y ¢, pero son incipits de un pentagrama, renders de Verovio y no escaneos, sin cambios de compás ni de armadura, sin tresillos y sin piano.
- Las **páginas reales** de INV-0002 se midieron con scripts de investigación que comparan notas y marcas, no el compás, la armadura, los tresillos o las partes.
- El responsable descargó, con permiso previo (#234, R1), tres verdades de OpenScore Lieder (CC0) y sus ediciones de Breitkopf en IMSLP (dominio público): *Ellens Gesang I* (cambios de compás y de armadura, ¢ y C), *Mondnacht* (voz y piano en 3/8, las páginas de INV-0002) y *Der stürmische Morgen* (C y tresillos con número y sin él). Otras tres verdades y tres páginas del PDF de *Winterreise* son del banco del estudio (#247).
- HOMR 0.7.0 no escribe nunca el símbolo del compás (ADR-0044), y en las páginas que siguen a un cambio no hay indicación impresa que leer.
- PyMuPDF no está en el entorno; `pdftoppm` (poppler), el de INV-0002, sí.

## Decisión

### 1. Un manifiesto versionado y los datos fuera del repositorio

`ml/experiments/reference_set_manifest.json` fija el conjunto: cada PDF y cada verdad con su ruta bajo `data/`, su sha256, su origen y su licencia; cada página con su PDF, su página del PDF (y la impresa), los compases de la verdad que contiene, los rasgos que cubre, notas sobre lo que la hace difícil y el sha256 de su imagen; y cada juego de predicciones de HOMR sobre PrIMuS con el sha256 de su manifiesto y una huella de sus predicciones (el sha256 de la lista de cada MusicXML y `failures.json` con su sha256). Los PDF, las verdades, las imágenes y las predicciones no se versionan.

- **Doce páginas**: las ocho de *Ellens Gesang I* (pp. 70-77 impresas), las pp. 9 y 10 de *Mondnacht* y las pp. 64 y 65 del PDF de *Winterreise* (60 y 61 impresas). Las páginas de la verdad salen de los saltos de página de OpenScore, que siguen la edición de Breitkopf, comprobados a ojo sobre el escaneo.
- **PrIMuS**: las predicciones de HOMR que ya hay (las 100 de `exp_03`/`exp_04` y las 2 000 de `exp_12`), sin transcribir de nuevo. Sus imágenes son renders de Verovio: el manifiesto y el resultado lo dicen.
- **Fuera**: las verdades y las páginas del banco del estudio (#247), para no medir con lo mismo que el estudio.
- **Los rasgos del manifiesto se comprueban**: el experimento los deduce de la verdad de los compases de cada página y falla si no coinciden; así un rango de compases mal puesto no pasa en silencio. El resultado dice qué casos cubren cada rasgo del criterio de #234 y cuáles faltan.
- **Si falta un archivo o su sha256 no es el del manifiesto**, el experimento falla antes de transcribir, con la lista de lo que falta o cambió. No hay modo sintético ni valores de reserva.

### 2. La imagen de cada página la genera el experimento

`exp_15_reference_set.py pages` (y `run`, si falta) rasteriza cada página con `pdftoppm -r 300 -f <p> -l <p> -png -singlefile` en `data/reference/pages/`. El manifiesto guarda la versión de `pdftoppm` (24.04.0) y el sha256 de cada imagen; si no coincide, el experimento falla: otra versión puede dar otros píxeles, y se mediría otra entrada. Se usa `pdftoppm` y no PyMuPDF porque es el de INV-0002 y PyMuPDF no está en el entorno (añadirlo obligaría a sincronizar el entorno, que desinstala HOMR; CLAUDE.md §7).

### 3. La transcripción

`HOMREngine` en CPU y sin preprocesado, como en producción (`--gpu` para la GPU), con la limitación de energía de Windows desactivada. El MusicXML de HOMR de cada página se guarda en la salida; `--reuse-predictions` lo reutiliza si es de la misma imagen y del mismo motor (versión de HOMR y dispositivo).

### 4. La comparación, rasgo a rasgo

**Alineación.** HOMR numera los compases de la página desde 1 y puede leer alguno de más o de menos (la indicación de cortesía de final de sistema, un compás partido entre dos sistemas). El compás p de la página (de 0 a n_verdad − 1) se compara con el compás q = redondeo(p · (n_HOMR − 1) / (n_verdad − 1)) de cada pentagrama leído, y un cambio o un tresillo cuenta como leído si está a una distancia de q no mayor que la tolerancia (`--tolerance`, 1 por defecto, que va en el resultado). Una columna de compases sin ningún evento en ningún pentagrama (la cortesía, si HOMR la lee como un compás aparte) se quita antes de alinear; un compás vacío en un solo pentagrama no, porque HOMR reparte a veces las notas de un sistema entre pentagramas de otra manera. Cada pentagrama de la lectura se compara con la verdad por separado (en estas piezas todos los pentagramas llevan el mismo compás y la misma armadura), emparejado en orden con los de la verdad: las unidades son pentagrama de la verdad × compás o cambio. Un pentagrama que HOMR no lee (o una página que no lee) cuenta como no leído, y uno de más no cuenta (se dice cuántos). Cada cambio leído empareja como mucho uno de la verdad (de los que están dentro de la tolerancia, el que lee el valor bueno y, si no hay, el más cercano), y los que no emparejan cuentan como cambios de más. Un pentagrama que HOMR no lee cuenta también como símbolo mal leído en cada compás que lo lleva.

1. **El compás por tramo, con su símbolo.** Cada inicio de tramo que la página imprime (al principio de la pieza o de una página que cambia, o a mitad de página) se busca entre los cambios que HOMR leyó: leído, métrica correcta y grafía correcta (`TimeSignature.same_notation`), aparte los del principio de página y los de mitad de página. Compás a compás, la métrica y la grafía; el símbolo C y ¢, con `time_symbol_agreement` (#236) sobre los compases alineados. Los compases de un tramo que empezó en una página anterior no llevan indicación impresa: se cuentan aparte (`inherited`), sin exigir a HOMR que la adivine. Un cambio leído al final de la página por la cortesía del cambio de la página siguiente cuenta como cortesía (leída y con qué métrica), no como un cambio de más; cualquier otro cambio que no corresponde a uno de la verdad, sí.
2. **La armadura**: la del principio de la página (que se imprime en cada sistema), cada cambio a mitad de página, la cortesía y la de cada compás. Sin armadura, Do mayor.
3. **Los tresillos por compás.** Un evento es de tresillo si su figura tiene un 3 en el denominador (ADR-0044 §3). Cada compás de la verdad con tresillos se busca en la lectura (en cualquier pentagrama) separando los marcados de los implícitos, que se leen del MusicXML de la verdad (`<tuplet show-number="none">`, implícito; con número, marcado; los dos, mixto); y cada compás leído con tresillos, en la verdad, emparejados uno a uno por cercanía (un compás leído no cuenta por dos de la verdad vecinos). Un compás de la verdad con figuras de tresillo y sin ningún `<tuplet type="start">` hace fallar el experimento: no se sabría de qué clase es.
4. **Las partes y los pentagramas**: cuántas partes y cuántos pentagramas por parte, en el orden del `ScoreIR` (las dos lecturas pasan por la misma importación).

**PrIMuS**: el compás inicial de cada incipit frente a su verdad MEI (numerador, denominador, métrica y grafía, con la tabla de confusiones) y el símbolo en todos sus compases con `time_symbol_agreement`. Lo que el dominio no admite (una verdad o una predicción ilegible) se registra por incipit y no se mide, como en `exp_12`; los incipits que HOMR no transcribió (`failures.json`) se cuentan aparte. Cada proporción de PrIMuS se da sobre los incipits medidos y, además, con los fallos de HOMR (no transcritos o ilegibles) como mal leídos (`*_with_failures`).

### 5. La salida

`reference_set_summary.json` (con `run_info`, `simulated: false`, la tolerancia, la cobertura, las proporciones principales con su numerador y denominador, el detalle de cada página y de cada juego de PrIMuS y la justificación del tamaño de muestra), `reference_set_pages.csv`, `reference_set_primus.csv`, `exp_15_run_info.json` y `reference_set_predictions/`. Por defecto en `results/`; con `--output-dir`, donde se diga.

## Consecuencias

- #237, #238 y #239 tienen una línea base medida con páginas impresas reales y su verdad, que se repite con un comando, y el mismo experimento mide después sus cambios.
- **Las muestras son pequeñas**: doce páginas, dos cambios de compás y dos de armadura a mitad de página (seis unidades de cada uno, una por pentagrama de la verdad) y seis compases con tresillos, dos de ellos implícitos y de la misma página. Las proporciones van con su numerador y su denominador, y no se extrapolan.
- **La verdad es la de OpenScore**, que puede no coincidir en todo con la edición de Breitkopf (dónde imprime el número de un tresillo, una cortesía); el manifiesto anota lo comprobado a ojo.
- **La alineación es aproximada**: con una tolerancia de un compás, una página con muchos compases de más o de menos puede contar como leído un cambio que HOMR puso cerca, o al revés. La tolerancia va en el resultado y se puede cambiar.
- Otra versión de `pdftoppm` obliga a actualizar el manifiesto a propósito.

## Alternativas consideradas

- **Alinear por contenido** (notas, con programación dinámica): más exacto ante compases de más o de menos, pero mucho más complejo, y depende de que HOMR lea bien las notas, que no es lo que se mide aquí. Se descarta mientras la alineación proporcional con tolerancia baste.
- **Renderizar la verdad** (Verovio o MuseScore) en vez de escanear: daría páginas sin el ruido de un escaneo, que es justo lo que no tiene PrIMuS.
- **Usar también las páginas del banco del estudio**: más casos, pero se mediría el reconocimiento con lo mismo que el estudio.
- **PyMuPDF para rasterizar**: no está en el entorno, y añadirlo obliga a sincronizarlo.
