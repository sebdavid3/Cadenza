# ADR-0060: La voz por encima del piano: las partes en el orden de la página y el piano en los dos pentagramas de abajo

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0005, ADR-0010, ADR-0018, ADR-0032, ADR-0041, ADR-0045 y ADR-0056, CLAUDE.md §8 y §9)
- **Relacionado:** [ADR-0018](ADR-0018-homr-como-unico-motor-omr.md), [ADR-0041](ADR-0041-titulo-compositor-e-instrumentos-de-la-sesion.md), [ADR-0045](ADR-0045-nombre-e-instrumentos-de-la-sesion-en-la-web.md), [ADR-0056](ADR-0056-conjunto-de-referencia-del-compas-tresillos-armaduras-y-voz-con-piano.md), [#239](https://github.com/sebdavid3/Cadenza/issues/239), [#238](https://github.com/sebdavid3/Cadenza/issues/238), [#247](https://github.com/sebdavid3/Cadenza/issues/247), [#237](https://github.com/sebdavid3/Cadenza/issues/237), [ADR-0057](ADR-0057-banco-de-partituras-del-estudio.md)

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

1. **Reagrupar los pentagramas en el `ScoreIR` después de HOMR** (por ejemplo, si el gran pentagrama tiene dos claves de sol y la parte suelta la de fa). Descartada: cuando HOMR lee la voz y la mano derecha como un gran pentagrama, a menudo las mezcla en un solo pentagrama, y eso no se separa después; y las claves no bastan (en *Der stürmische Morgen* p. 65 la mano derecha empieza en clave de fa).
2. **Elegir siempre el par de abajo en un sistema de tres.** Descartada: tiraría la llave cuando HOMR la distingue de la barra del sistema, y un piano por encima de otro pentagrama saldría mal aunque su llave se viera.
3. **Penalizar en la puntuación lo que el elemento se sale del par.** Descartada: la barra del sistema se sale de los dos pares casi lo mismo, y el resultado seguiría dependiendo del hueco de la letra.
4. **Corregirlo en HOMR (un fork o un parche del paquete).** Descartada: HOMR se instala como extra a mano (CLAUDE.md §7) y un fork obligaría a mantenerlo; la envoltura en el adaptador, como la de `detect_title`, cubre el caso y falla si HOMR cambia.
5. **Deducir el instrumento de la parte, como pide #239.** No se hace por §4: lo impiden ADR-0041 y ADR-0045.
