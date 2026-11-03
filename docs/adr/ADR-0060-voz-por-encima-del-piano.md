# ADR-0060: La voz por encima del piano: las partes en el orden de la página y el piano en los dos pentagramas de abajo

- **Estado:** Aceptado; §2 enmendado por #325 (2026-11-03): el piano se lee emparejado y solo, y se combina ([§Enmienda de #325](#enmienda-de-325-2026-11-03-el-piano-leído-emparejado-y-solo-y-combinado))
- **Fecha:** 2026-11-02
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0005, ADR-0010, ADR-0018, ADR-0032, ADR-0041, ADR-0045 y ADR-0056, CLAUDE.md §8 y §9)
- **Relacionado:** [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md), [ADR-0041](ADR-0041-titulo-compositor-e-instrumentos-de-la-sesion.md), [ADR-0045](ADR-0045-nombre-e-instrumentos-de-la-sesion-en-la-web.md), [ADR-0056](ADR-0056-conjunto-de-referencia-del-compas-tresillos-armaduras-y-voz-con-piano.md), [#239](https://github.com/sebdavid3/Cadenza/issues/239), [#238](https://github.com/sebdavid3/Cadenza/issues/238), [#247](https://github.com/sebdavid3/Cadenza/issues/247), [#237](https://github.com/sebdavid3/Cadenza/issues/237), [ADR-0057](ADR-0057-banco-de-partituras-del-estudio.md), [#325](https://github.com/sebdavid3/Cadenza/issues/325)

---

## Contexto

El banco del estudio (#247) vio dos fallos en las piezas de voz y piano (TS-02, TS-03 y TS-04): en TS-04 la voz se dibujaba debajo del piano, y en TS-02 y TS-03 la voz y la mano derecha salían en una parte, con el compás puesto dos veces y la llave del piano abarcando la voz. Las causas, comprobadas el 2026-11-02 sobre el MusicXML que da HOMR 0.7.0:

1. **La importación cambiaba el orden de las partes.** HOMR escribe las partes de arriba abajo («Voice» y «Piano» en TS-04). music21 crea un `StaffGroup` para cada parte de varios pentagramas, y `_group_parts` ponía primero los grupos y después las partes de un pentagrama: el piano pasaba delante de la voz. Lo mismo les pasaba a las seis verdades de OpenScore de `data/reference/truth/` (voz y piano).
2. **HOMR juntaba la voz con la mano derecha.** En cada sistema, HOMR une dos pentagramas vecinos en un gran pentagrama si un elemento alto a la izquierda los abarca, y elige el par en el que ese elemento se solapa más (`MultiStaff._select_grandstaffs`). En las páginas de voz y piano, la barra que une los tres pentagramas al principio del sistema cuenta como uno de esos elementos (a veces fundida con la llave por el ensanchado de la imagen): abarca los dos pares y gana el de arriba cuando el hueco de la letra, entre la voz y la mano derecha, es mayor que el que hay entre las manos. La parte que HOMR llama «Piano» era entonces la voz con la mano derecha, y la que llama «Voice», la mano izquierda. Pasa sistema a sistema: en una misma página unos sistemas salían bien y otros no (*Mondnacht* pp. 9 y 10), y en TS-02, TS-03 y *Der stürmische Morgen* p. 65, en todos (HOMR en la GPU).
3. **`exp_15` no lo veía.** Compara cuántas partes hay y cuántos pentagramas tiene cada una (ADR-0056 §4.4), y la verdad pasaba por la misma importación: el 12 de 12 de la línea base era [2, 1] frente a [2, 1], con el contenido de los pentagramas cambiado de sitio.

El alcance acordado de #239 son las partituras de piano con una voz o un instrumento por encima, en tres pentagramas. La letra queda fuera (#263).

## Decisión

### 1. La importación conserva el orden de la página

`_group_parts` (`packages/interchange`) devuelve las partes en el orden del documento: cada grupo va donde está su primera parte en `Score.parts`. La exportación ya escribía las partes en el orden del `ScoreIR`, así que lo exportado vuelve a importarse igual.

**Huella** (el sha256 del `to_primitive()` de `read_score` de los 4 439 archivos de `data/` que leen los experimentos: las verdades de los manifiestos, las predicciones de PrIMuS y las verdades de referencia), antes y después: cambian 6, las seis verdades de OpenScore (`lc4987640`, `lc5007180`, `lc5007182`, `lc5013945`, `lc5023603` y `lc6181353`), que pasan de [2, 1] a [1, 2], la voz arriba. Ninguna de PrIMuS cambia: son de una parte. Las cifras de PrIMuS (`exp_03` a `exp_14`) no se mueven.

### 2. En un sistema de tres pentagramas, el piano son los dos de abajo

> Enmendado por #325: el piano encontrado así se lee de dos maneras, emparejado (lo que sigue) y con cada pentagrama solo, y se combina sistema a sistema y mano a mano (§Enmienda de #325).

`HOMREngine` sustituye, al importar HOMR y como ya hace con `detect_title` (#106), `MultiStaff._select_grandstaffs` por una envoltura (`cadenza.omr.adapters.homr_grand_staff`):

- Solo en los sistemas de **tres pentagramas**. Los de dos (el piano solo) o de más de tres siguen como los deja HOMR.
- Un elemento que abarca al menos la mitad del alto de **cada uno de los tres** pentagramas no decide el par: es la barra del sistema. HOMR elige el par con su misma puntuación entre los demás elementos (la llave del piano, que solo abarca dos).
- Si solo hay elementos de los que abarcan los tres, el piano son **los dos de abajo**, como en toda partitura de una voz o un instrumento por encima del piano.
- Si la versión de HOMR no tiene `_select_grandstaffs`, importar HOMR falla con un mensaje claro: sin la sustitución, la voz y la mano derecha volverían a juntarse en silencio.

No se toca el resto de HOMR: el reconocimiento de cada pentagrama, las claves y los compases son los suyos. No es una etapa tras HOMR como la de #237 (el compás y los tresillos sobre el `ScoreIR`): ocurre dentro de HOMR, antes de que lea los pentagramas, porque después no se puede deshacer (la voz y la mano derecha leídas como un gran pentagrama salen mezcladas en un mismo pentagrama cuando el modelo no separa las dos alturas). La etapa de #237 recibe ya la voz como primera parte.

### 3. `exp_15` mide también dónde va el contenido de cada pentagrama

`compare_page` gana `staves`: para cada pentagrama de la verdad y cada compás de la página con notas en él (las unidades), toma el compás alineado del pentagrama leído del mismo orden y compara su multiconjunto de alturas con el de cada pentagrama de la verdad en ese compás (F1 de las alturas). Está `in_place` si se parece más a su pentagrama que a cualquier otro, o si lo lee entero aunque otro sea igual (una mano que dobla la voz); `elsewhere` si se parece más a otro (o igual, sin leerlo entero); `missing` si no se leyó o no comparte ninguna altura con ninguno. La alineación es la proporcional de ADR-0056: un compás de más o de menos en la lectura también puede dejar el contenido en `elsewhere` o en `missing`, así que la métrica mezcla el cambio de pentagrama con la desalineación. El resumen da `staves_in_place`, `staves_elsewhere` y `staves_missing` con su numerador y denominador, y el CSV de las páginas, una columna por cuenta. Lo demás de ADR-0056 no cambia.

### 4. El nombre y el instrumento de las partes no se deducen

#239 pide que el instrumento salga «del formulario (#235) y, si no se indica, de la propia parte (voz o piano)», y que las partes se importen «con su nombre». ADR-0041 (§1, §3 y alternativas 1 y 2) y ADR-0045 (§1 y alternativa 3) deciden lo contrario: el nombre y el instrumento son datos de la sesión, los indica la persona, y no se deducen del número de pentagramas ni del nombre que da HOMR, que es justo el número de pentagramas («Voice» si tiene uno, «Piano» si tiene dos). Si un issue y un ADR se contradicen, prevalece el ADR (CLAUDE.md §1): no se cambia. Lo que sí cambia con §1 y §2 es que el instrumento del formulario cae en su parte: «Parte de arriba» es la voz y «Segunda parte», el piano, y el MusicXML exportado lleva «Voz» y «Piano» con su sonido. Deducirlos queda como decisión del responsable.

### 5. Verificado contra la API real (2026-11-02)

Con HOMR en la GPU, una API local y la web del worktree, a 1440 y a 390 px, en TS-02, TS-03 y TS-04 del banco y en las pp. 2 y 7 de *Ellens Gesang I*:

- Las cinco sesiones tienen la voz como parte 0 (un pentagrama, clave de sol) y el piano como parte 1 (sol y fa), y OSMD dibuja la voz arriba, sola, y la llave del piano en los dos de abajo.
- En los tres pentagramas (TS-04 a 1440 y TS-02 a 390): elegir una nota (la barra dice «Pentagrama 1», «2» o «3»), subirla o bajarla, deshacer, reproducir (avanza el compás) y descargar el MusicXML (la voz primero, el piano después, con la corrección en su pentagrama). Con los instrumentos de la sesión, el MusicXML lleva «Voz» y «Piano».
- **#238:** la p. 2 de *Ellens Gesang I* cambia de cinco bemoles a tres sostenidos en el c. 11 y la p. 7, de tres sostenidos a cinco bemoles en el c. 19. OSMD dibuja la armadura de cortesía al final del sistema y la nueva en el compás del cambio en los tres pentagramas, a 1440 y a 390 px, y el MusicXML exportado lleva el `<key>` del cambio en ese compás en las dos partes.

## Consecuencias

### Positivas

- **Medido con `exp_15`** (las doce páginas de voz y piano de #234, HOMR 0.7.0 en CPU, con la salida en el scratchpad). **Antes:** el script de `exp_15` de esta rama, con la métrica nueva, sobre los paquetes de `dev` (1771ffc) y con `--reuse-predictions` sobre las predicciones de HOMR de `results/exp_15/` (las de la línea base de #234); las demás cifras coinciden con la línea base. **Después:** esta rama entera, transcribiendo de nuevo. partes y pentagramas por parte 12 de 12 antes y después (antes [2, 1] en la verdad y en la lectura; después [1, 2] en las dos); los compases leídos por pentagrama, como antes salvo la p. 7 de *Ellens Gesang I* (24, 24 y 23 → 24, 23 y 23, de 23); el contenido de cada pentagrama en su sitio pasa de 126 de 734 unidades (17,2 %) a 698 de 734 (95,1 %), con 6 en otro pentagrama y 30 sin leer. El resto de `exp_15` se mueve en un compás: la armadura bien leída, de 781 a 782 de 789, y los compases heredados sin compás, de 409 a 410 de 414, porque HOMR lee ahora los pentagramas en otros grupos. Los cambios de armadura siguen 6 de 6 detectados y correctos (#238).
- La voz se dibuja arriba, la llave del piano abarca solo el piano y el compás sale una vez por pentagrama, como en la página.
- El instrumento indicado al subir llega a su parte (ADR-0041 §3).

### Negativas / Riesgos

- **Depende de un método privado de HOMR.** Otra versión puede cambiarlo; la importación falla si desaparece, y una prueba con el `MultiStaff` real lo comprueba cuando HOMR está instalado.
- **La barra del sistema tiene que cubrir la mitad de cada pentagrama.** Si cubre menos de la mitad del de la voz (una página torcida o una barra cortada), cuenta como llave y HOMR puede volver a elegir el par de arriba. No pasa en las páginas medidas.
- **La regla supone la voz arriba.** Un sistema de tres pentagramas con el gran pentagrama arriba y otro debajo (el órgano con el pedal), sin una llave que HOMR distinga de la barra del sistema, saldría con el par de abajo. Está fuera del alcance (#239).
- **Una sesión anterior no cambia:** su `ScoreIR` ya está guardado con el orden de antes. El cambio vale para lo que se transcribe después y para lo que se importa de nuevo.
- La línea base guardada en `results/exp_15/` no tiene la métrica del contenido de los pentagramas: hay que volver a medir `exp_15` para tenerla.

## Alternativas consideradas

1. **Reagrupar los pentagramas en el `ScoreIR` después de HOMR** (vuelto a medir en #325, alternativa 1 de la enmienda; por ejemplo, si el gran pentagrama tiene dos claves de sol y la parte suelta la de fa). Descartada: cuando HOMR lee la voz y la mano derecha como un gran pentagrama, a menudo las mezcla en un solo pentagrama, y eso no se separa después; y las claves no bastan (en *Der stürmische Morgen* p. 65 la mano derecha empieza en clave de fa).
2. **Elegir siempre el par de abajo en un sistema de tres.** Descartada: tiraría la llave cuando HOMR la distingue de la barra del sistema, y un piano por encima de otro pentagrama saldría mal aunque su llave se viera.
3. **Penalizar en la puntuación lo que el elemento se sale del par.** Descartada: la barra del sistema se sale de los dos pares casi lo mismo, y el resultado seguiría dependiendo del hueco de la letra.
4. **Corregirlo en HOMR (un fork o un parche del paquete).** Descartada: HOMR se instala como extra a mano (CLAUDE.md §7) y un fork obligaría a mantenerlo; la envoltura en el adaptador, como la de `detect_title`, cubre el caso y falla si HOMR cambia.
5. **Deducir el instrumento de la parte, como pide #239.** No se hace por §4: lo impiden ADR-0041 y ADR-0045.

## Enmienda de #325 (2026-11-03): el piano, leído emparejado y solo, y combinado

### Contexto

La segunda revisión del banco del estudio (ADR-0057 §Segunda revisión) vio que §2 empeora la lectura de TS-03: con las dos manos emparejadas como un gran pentagrama, HOMR pierde la vuelta a la clave de fa del c. 7 de la mano izquierda, notas y alteraciones del c. 6 y los tresillos de la mano derecha. #325 propone dejar que HOMR elija sus pares y reagrupar después las partes. Antes de decidir se midieron cuatro lecturas de las mismas imágenes (HOMR 0.7.0 en CPU; el banco, comparado con su verdad como en la revisión: lo que falta y lo que sobra por pentagrama, por lo que se ve; en las páginas de `exp_15`, la lectura de HOMR, sin la etapa del compás). **Las cifras son exploratorias**, de los scripts del scratchpad de #325, no de un experimento de `ml/experiments`:

| Lectura del piano | TS-02 (faltan / sobran) | TS-03 | TS-04 | `exp_15` (faltan / sobran)* |
|---|---|---|---|---|
| Emparejado (§2, #239) | 3 / 2 | 48 / 45 | 1 / 1 | 715 / 605 |
| La elección de HOMR (sin §2), reagrupada sistema a sistema | 8 / 8 | 28 / 26 | 1 / 1 | 1 550 / 2 019 |
| Cada pentagrama solo | 8 / 8 | 31 / 30 | 16 / 16 | 646 / 571 |
| **Combinado (esta enmienda)** | **3 / 2** | **26 / 25** | **1 / 1** | **547 / 444** |

\* En los tres pentagramas de las doce páginas, lo que falta y lo que sobra en cada compás de la verdad frente al compás alineado de la lectura (la alineación proporcional de ADR-0056; inicio, nota o silencio, altura y figura). Las verdades de OpenScore no siempre coinciden con la edición escaneada, así que las cifras solo sirven para comparar las lecturas entre sí. Las de la primera y la última fila se repitieron con la versión final sobre las predicciones de `results/exp_15_compas/` y `results/exp_15_piano_combinado/`, y dan lo mismo.

Lo que se vio:

1. **Ninguna lectura gana siempre.** Emparejadas, las manos comparten las barras y el ritmo de una ayuda al de la otra (en TS-02 y TS-04 la mano izquierda sola lee semicorcheas donde hay corcheas y figuras con puntillo donde no las hay); solas, HOMR lee mejor las claves (TS-03 conserva la clave de fa), pero pierde tresillos que emparejada lee.
2. **La elección de HOMR no se puede reagrupar.** Cuando empareja la voz con la mano derecha, a menudo escribe las dos en el pentagrama de arriba: en *Ellens Gesang I* p. 1, los sistemas 3 y 4 salen con 65 y 66 notas en el pentagrama de la voz y ninguna en el de la mano derecha (HOMR pasa todo arriba si no lee una clave abajo en los primeros símbolos, `_only_keep_lower_staff_if_there_is_a_clef`). Es lo que ya decía la alternativa 1. Además elige el par sistema a sistema, así que una misma parte es la voz en unos sistemas y la voz con la mano derecha en otros. En TS-03 sí separa las manos, y por eso da 28 / 26; en `exp_15`, reagrupando sistema a sistema con la elección registrada, da más del doble de errores que emparejado.
3. **Los errores de una lectura se notan sin la verdad.** Donde una lectura se equivoca en las figuras, sus compases dejan de durar lo que duran los demás de esa mano. Elegir en cada sistema y cada mano la lectura con menos compases de duración distinta de la habitual mejora a las dos (tabla).

### Decisión

**§2 cambia así.** La elección del par del piano de un sistema de tres pentagramas es la misma (la barra del sistema no decide; sin llave propia, los dos de abajo), pero el piano se lee de dos maneras y se combina:

1. **Dos lecturas de la página.** `HOMREngine` lee la página con el piano emparejado, como en §2. Si en algún sistema de tres pentagramas el piano son los dos de abajo, la lee otra vez con cada pentagrama del sistema solo (`homr_grand_staff.reading`, `PianoReading.PAIRED` y `ALONE`). Las demás páginas se leen una vez, como antes.
2. **La combinación** (`cadenza.omr.adapters.homr_piano`), sistema a sistema y mano a mano, sin la verdad:
   - La duración habitual de cada mano es la de la lectura emparejada: la suma más repetida de sus compases con notas (a igualdad, la mayor). Un compás es **irregular** si no dura eso o si se quedó sin notas.
   - De cada mano se toma la lectura sola si tiene la misma duración habitual que la emparejada, en ese sistema **menos compases irregulares** **y los mismos compases** que ella. Si no, la emparejada. Así las dos manos de cada sistema tienen los mismos compases, y el piano tiene los mismos que con §2 frente a la voz. La habitual se exige igual porque una mano sola que se equivoca igual en casi todos los compases cambia su propia habitual y parecería regular.
   - Los sistemas se cuentan en el MusicXML de HOMR (`<print new-system="yes">`).
   - Donde un sistema sale de otra lectura que el anterior, su primer compás lleva la clave, la armadura y el compás que rigen en esa lectura si no son los que regían (HOMR no los repite en cada sistema). Los compases se numeran de nuevo, y las ligaduras de expresión se quedan si tienen sus dos extremos y se numeran como las numera la importación.
   - La voz sale de la lectura emparejada; las partes, la llave y el orden de la página son los de §1 y §2.
   - La elección de cada sistema queda en el registro del adaptador (`Piano por sistema: ...`).
3. **El MusicXML.** Si alguna mano sale de la lectura sola, `transcribe_musicxml` devuelve el del `ScoreIR` combinado, escrito por el exportador de Cadenza: importado da el mismo `ScoreIR` (salvo, a veces, cómo se emparejan los extremos de una ligadura de expresión, como en cualquier exportación). Si no se elige ninguna, devuelve el de la lectura emparejada tal cual, con sus ligaduras y sus saltos de sistema, como §2. Lo usan igual `transcribe` y `exp_15`.
4. **Las reservas.** Queda la emparejada, la transcripción de §2, si:
   - la segunda lectura falla, por lo que sea;
   - las lecturas no son las de una página de voz y piano: la emparejada con [1, 2], la otra con tres partes de un pentagrama y los mismos sistemas, también en la voz (HOMR se salta el sistema de un pentagrama vacío, y si se saltara uno distinto en cada lectura se compararían sistemas distintos);
   - la combinación falla, o lo exportado no se vuelve a importar.

### Medición

**`exp_15`** (las doce páginas de voz y piano, HOMR 0.7.0 en CPU, `--meter-features all` como en producción, transcribiendo de nuevo con esta rama). Antes: `results/exp_15_compas/` (§2 y la etapa del compás de #237). Después: `results/exp_15_piano_combinado/`.

| | Antes | Con la enmienda |
|---|---|---|
| Unidades en su pentagrama | 698 de 734 (95,1 %) | **701 de 734 (95,5 %)** |
| En otro pentagrama | 6 | 6 |
| Sin leer | 30 | 27 |
| Compases leídos con tresillo (de ellos, en la verdad) | 6 (4) | 4 (4) |

Solo cambian dos páginas: en *Mondnacht* p. 10, tres unidades sin leer pasan a su pentagrama, y en p. 9 desaparecen los dos compases con tresillos que la página no tiene. Todo lo demás da lo mismo: la disposición y las partes (12 de 12), el compás (375 de 375 compases impresos, 120 de 120 con su símbolo, sin cambios espurios), las armaduras (782 de 789 compases), los tresillos marcados (4 de 4) y PrIMuS, que no pasa por esta combinación. `exp_15` no mide las notas de cada pentagrama: eso lo dice la tabla del contexto, que es exploratoria.

**El banco** (las cinco partituras, con el MusicXML de `HOMREngine` de la rama, comparadas con la verdad como en la segunda revisión; exploratorio):

| | Calentamiento | TS-01 | TS-02 | TS-03 | TS-04 |
|---|---|---|---|---|---|
| `dev` (§2) | 0 / 0 | 12 / 12 | 3 / 2 | 48 / 45 | 1 / 1 |
| Con la enmienda | 0 / 0 | 12 / 12 | 3 / 2 | **26 / 25** | 1 / 1 |

TS-03 queda mejor que sin §2 (28 / 26). Su mano izquierda sale de la lectura sola en los sistemas que la emparejada leía mal: conserva la vuelta a la clave de fa del c. 7, y los cc. 3 a 8 coinciden con la verdad. Lo que falta está en la mano derecha (los tresillos de los cc. 4 y 8 y la voz de abajo del c. 2) y en las ligaduras del c. 2 de la izquierda. En TS-02 y TS-04 no se elige ninguna mano sola, así que su MusicXML es, byte a byte, el de `dev`. Las tres siguen con la voz arriba y el piano en una parte de dos pentagramas.

### Consecuencias

- **Las páginas de voz y piano tardan más del doble en transcribirse**: HOMR las lee dos veces, segmentación incluida, y la combinación pasa por el `ScoreIR`. En CPU, TS-02 a TS-04 pasan de 5,5-7,2 s a 14,0-16,3 s. Las páginas sin piano debajo de otro pentagrama (el calentamiento, TS-01, PrIMuS) tardan lo mismo que antes. La duración que mide el estudio empieza al cargar la sesión, ya transcrita (protocolo §3.4), así que esta espera no entra en ella; la de producción se mide en #269. El candado de HOMR (`_HOMR_LOCK`) se mantiene durante las dos lecturas, así que una transcripción que espera a otra de voz y piano espera el doble.
- **`transcribe_musicxml` deja de dar el MusicXML de HOMR tal cual en las páginas en que alguna mano sale de la lectura sola**: pierde los saltos de sistema, las repeticiones y las voltas que el `ScoreIR` no modela. Los experimentos de OMR-NED usan PrIMuS, de un pentagrama, y no cambian. En el banco, solo TS-03.
- **`exp_15 --reuse-predictions`** reconoce las predicciones por la imagen, el motor, la versión de HOMR y el dispositivo, no por la versión de Cadenza: las de antes de esta enmienda no deben reutilizarse.
- **La señal de la elección es la duración de los compases.** Un error que no cambia lo que dura un compás (una clave perdida con las figuras bien, una altura) no se ve: si las dos lecturas de una mano tienen los mismos compases irregulares en un sistema, gana la emparejada aunque haya perdido una clave. En TS-03 la mano izquierda emparejada, además de la clave, pierde figuras, y por eso se elige la sola.
- **La duración habitual es la de toda la página**, no la de cada tramo de compás como en ADR-0059. En una página con un cambio de compás, los compases bien leídos del tramo más corto cuentan como irregulares en las dos lecturas (en *Ellens Gesang I* p. 2, los diez de 3/4), y una lectura que leyera mal uno de ellos de modo que durara lo habitual ganaría. No pasa en ninguna página medida; la habitual por tramo obligaría a volver a medir.
- **Las ligaduras de prolongación y los reguladores** no se renumeran en el empalme: HOMR 0.7 no los escribe. Si una versión futura los escribe, una ligadura que cruce el límite de un sistema empalmado puede quedar sin pareja.
- **Depende de otro detalle de HOMR**: la segunda lectura no empareja los pentagramas del sistema; si HOMR cambia cómo agrupa las partes, la combinación no encaja y queda la emparejada.

### Alternativas consideradas

1. **La elección de HOMR y reagrupar las partes después (la propuesta de #325).** Descartada por la medición (punto 2 del contexto): TS-03 mejora, pero TS-02 empeora y en `exp_15` la voz y la mano derecha salen en el mismo pentagrama en muchos sistemas, cosa que no se separa después.
2. **Leer siempre cada pentagrama solo.** Descartada: TS-04 pasa de 1 / 1 a 16 / 16 y TS-02 de 3 / 2 a 8 / 8; en `exp_15` el contenido en su sitio sube, pero las manos de un sistema pueden tener otros compases y la etapa del compás deja de reconocer el de esas partes (la grafía del compás bien leída bajaba de 375 a 351 de 375).
3. **Dejar §2 como estaba.** Descartada: TS-03 seguiría pidiendo 79 ediciones (ADR-0057).
4. **Elegir por sistema, las dos manos de la misma lectura.** Descartada: en una primera medición del piano de `exp_15` daba más errores que elegir mano a mano, y en TS-03 lo mejor es la mano derecha emparejada y la izquierda sola, que no se puede elegir así.
5. **Segmentar una sola vez.** HOMR tiene una caché pública de la segmentación (`ProcessingConfig(enable_cache=True)`): guarda la salida de segnet comprimida con lzma junto a la imagen, con su sha256 y la versión del modelo, y la segunda lectura la cargaría en lugar de segmentar otra vez, con la misma detección de pentagramas en las dos. No se ha medido lo que ahorra frente a lo que cuesta comprimir y descomprimir. Queda como mejora de la latencia si #269 la pidiera.
