# INV-0002: Audiveris frente a HOMR — matices, compás con su símbolo y tresillos implícitos

- **Fecha de la medición:** 2026-10-24 (cifras de comparación regeneradas el 2026-10-26)
- **Issue:** [#233](https://github.com/sebdavid3/Cadenza/issues/233); plan de cierre [#231](https://github.com/sebdavid3/Cadenza/issues/231); trabajo futuro [#262](https://github.com/sebdavid3/Cadenza/issues/262)
- **Relacionado:** [ADR-0018](../adr/ADR-0018-homr-como-unico-motor-omr.md), [ADR-0016](../adr/ADR-0016-transcripcion-sincrona-vs-asincrona.md), [ADR-0024](../adr/ADR-0024-transcripciones-simultaneas.md), [ADR-0031](../adr/ADR-0031-marcas-de-notacion-en-el-score-ir.md), [INV-0001](INV-0001-salidas-internas-homr-bbox-y-confianza.md)
- **Material:** [`INV-0002/`](INV-0002/) (scripts de comparación y receta de la imagen de Audiveris)
- **Estado:** Completada. Audiveris no se integra en la entrega de noviembre de 2026; queda como trabajo futuro ([#262](https://github.com/sebdavid3/Cadenza/issues/262))

> **Todas las cifras de este documento son mediciones del 2026-10-24 sobre pocas páginas** (dos de un lied, un manuscrito y una página de la Sonata). Antes de citar cualquiera hay que regenerarla con el procedimiento de la §5 (`CLAUDE.md` §8.4).

---

## 1. Motivación

HOMR 0.7.0, el único motor OMR de Cadenza (ADR-0018), no da cuatro cosas que una partitura real necesita:

- **Matices.** Las dinámicas y los reguladores están comentados en su vocabulario (`homr/transformer/vocabulary.py`, líneas 69–80): el modelo no los produce.
- **Numerador del compás.** El vocabulario solo tiene `timeSignature/{denominador}`. El numerador lo deduce `find_division_and_time_signature_nominator` (`homr/music_xml_generator.py`) con la mediana de lo que suman los compases de la parte.
- **C y ¢.** No los distingue.
- **Tresillos implícitos.** `_fix_over_eager_tuplets` (`homr/transformer/vocabulary.py`) quita los tresillos de los compases que suman menos que la **mediana** de la página (`_get_typical_duration_of_measures`; la variable se llama `mean`, pero es una mediana), y los tresillos que la partitura solo marca al principio salen como corcheas.

La pregunta: ¿puede Audiveris 5.11.0, ejecutado sin modificar como programa aparte, completar a HOMR donde acierta?

## 2. Material y método

### 2.1. Entorno

- **Audiveris 5.11.0** (release del 2026-07-11), paquete `Audiveris-5.11.0-ubuntu24.04-x86_64.deb` del release oficial (77 716 868 bytes, sha256 `f20113aaa33b3149ec8d6a09b2a7963360e65fafd92d69389987a85bbc3ec7a3`), licencia AGPL-3.0.
- **Imagen Docker** de [`INV-0002/Dockerfile.audiveris`](INV-0002/Dockerfile.audiveris), de 636 MB, en contenedores desechables del servidor r2d2, en CPU. Al terminar se borraron las imágenes y las carpetas de prueba. Tres detalles de la imagen:
  - instalar el paquete con `apt-get` falla en un contenedor («Errors were encountered while processing: audiveris»). Su `postinst` solo registra el menú y los tipos de archivo del escritorio (`xdg-desktop-menu`, `xdg-mime`); es la causa probable, deducida de leerlo: el mensaje del error no se vio. Por eso el `.deb` se extrae con `dpkg-deb -x`;
  - Audiveris carga GTK 3 al arrancar aunque vaya sin interfaz: sin `libgtk-3-0t64` falla con `UnsatisfiedLinkError: Unable to load library 'gtk-3'`, y con él la imagen pasa de 439 a 636 MB;
  - necesita `JAVA_TOOL_OPTIONS=-Djava.awt.headless=true`.
- **Orden de Audiveris:**
  ```bash
  /opt/audiveris/bin/Audiveris -batch \
      [-constant org.audiveris.omr.sheet.ProcessingSwitches.implicitTuplets=true] \
      -transcribe -export -output <carpeta> -- <imagen>
  ```
  `implicitTuplets` vale `false` por defecto (`ProcessingSwitches.java`). Con `true`, `TupletGenerator` añade tresillos a las voces que empiezan en el primer tiempo y duran exactamente 3/2 de lo que exige el compás; su código cita la Sonata *Claro de luna* como caso.
- **HOMR 0.7.0** con el adaptador de Cadenza, `HOMREngine(use_gpu=False).transcribe_musicxml(<imagen>)`, en la máquina de desarrollo (Windows, CPU). Sus tiempos no se comparan con los de Audiveris, que se midieron en otra máquina.

### 2.2. Páginas y verdad

| Página | Origen y licencia | Verdad | Para qué |
|---|---|---|---|
| *Mondnacht* (Schumann, Liederkreis op. 39 n.º 5), páginas 9 y 10 | IMSLP #270920: *Robert Schumanns Werke*, serie XIII, Leipzig, Breitkopf & Härtel, 1885 (plancha R.S. 127, ed. Clara Schumann), PDF de 22 páginas; dominio público según IMSLP. Páginas 9 y 10 a 300 ppp con `pdftoppm -r 300 -f 9 -l 10 -png` (2968×3904 y 2966×3902 px) | OpenScore Lieder `lc4987640.mscx` (CC0), exportado a MusicXML con MuseScore 3.6.2: voz y piano, 3/8, 68 compases | Notas y marcas en una página impresa real |
| *Mondnacht* «foto» | [`degradar_foto.py`](INV-0002/degradar_foto.py) sobre las dos páginas: giro de 1,5°, desenfoque gaussiano de 1,8, luz desigual, ruido (σ = 9) y JPEG de calidad 70, con semilla 205 | La misma | Robustez ante una foto |
| *An die Musik* (Schubert, D 547), autógrafo | Wikimedia Commons, `Franz_von_Schober,_An_die_Musik.jpg` (facsímil de W. Dahms, 1913; 3694×4681 px, sha1 `5a1f2e635840fa6ca73f8fc1f394a57cd1487a52`); dominio público según Commons | OpenScore Lieder `lc6180725.mscx` (CC0), en ¢. Es una edición, no el autógrafo: puede no coincidir en todo | Un manuscrito, y el compás ¢ |
| Sonata *Claro de luna* (Beethoven, op. 27 n.º 2, 1.er mov.), compases 1–11 | Página del responsable (1127×716 px, grabado digital). No se versiona | Sin verdad completa: comparación entre motores y lectura a ojo | ¢ y tresillos marcados solo en el compás 1 |

**Dinámicas y reguladores impresos.** OpenScore añade dinámicas invisibles para la reproducción, y el MusicXML de MuseScore 3.6.2 pierde la marca de invisible. Por eso lo impreso se toma del `.mscx`:
- ***Mondnacht*:** 34 dinámicas, de las que 29 son invisibles. Quedan **5 impresas**: *p* en los compases 6 y 28 de la voz, *p* en los compases 23 y 61 y *pp* en el 67 del piano. Los 24 reguladores son visibles.
- **Autógrafo:** 6 dinámicas, una invisible (*f* en el compás 16). Quedan **5 impresas**: *p*, *pp*, *p* y dos *fp*. De 5 reguladores, uno es invisible: quedan **4**, los mismos que trae el MusicXML.

Ni las imágenes ni las partituras ni las salidas de los motores se versionan (`CLAUDE.md` §5); la sección «Cómo reproducirlo» dice cómo volver a obtenerlas.

### 2.3. Medidas

- **Notas** ([`comparar_mondnacht.py`](INV-0002/comparar_mondnacht.py) y [`comparar_autografo.py`](INV-0002/comparar_autografo.py)): coincidencia de multiconjuntos de (altura, duración) en toda la página, sin mirar dónde está cada nota, porque los motores reorganizan pentagramas y compases. «Solo altura» cuenta las que coinciden en altura sin mirar la duración, e incluye las que coinciden en las dos.
- **Marcas** ([`fusion.py`](INV-0002/fusion.py)): los compases de cada motor se emparejan con los de la verdad por sus alturas, con Needleman-Wunsch. Una marca está **bien colocada** si coincide en tipo y valor, grupo (voz o piano), compás y ataque, con una tolerancia de una semicorchea. La **precisión** es bien colocadas entre propuestas; la **cobertura**, bien colocadas entre las de la verdad.
- **Fusión** ([`fusion.py`](INV-0002/fusion.py)), sin usar la verdad: se emparejan los compases de Audiveris con los de HOMR, se descartan las marcas de compases poco parecidos (umbral 0, 0,5 o 0,7) y cada dinámica o regulador se ancla al ataque de HOMR más cercano del mismo grupo. Staccatos y calderones: los de HOMR.
- **Sonata** ([`comparar_sonata.py`](INV-0002/comparar_sonata.py)): compás, tresillos y suma de cada voz por compás, alturas por compás entre motores, marcas y lo que hace Cadenza con cada lectura (importación, posibles errores y exportación).
- **Compás impreso en cada salida** ([`compases.py`](INV-0002/compases.py)).

Los scripts importan `music21` directamente. `CLAUDE.md` §10 lo limita a `packages/interchange` dentro del producto; estos scripts de investigación no forman parte del producto, y comparan las salidas de los motores tal cual, antes de que Cadenza las importe.

## 3. Resultados

Las cifras de las §3.2 a §3.4 se regeneraron el 2026-10-26 con los scripts de [`INV-0002/`](INV-0002/) sobre las salidas guardadas el 2026-10-24, y coinciden con las de ese día. Los posibles errores de la Sonata dependen de las reglas de Cadenza: se regeneraron con las de `edb7f80`. Los tiempos (§3.1) no se pueden regenerar sin volver a ejecutar los motores. Las cifras de la Sonata no tienen verdad: son una comparación entre motores.

### 3.1. Tiempo (medido el 2026-10-24)

Una sola ejecución por imagen, en tiempo de pared de `docker run`: incluye arrancar el contenedor y la máquina virtual de Java. Se midió en r2d2, que a la vez sirve Cadenza e Immich.

| Imagen | Audiveris en r2d2, CPU |
|---|---|
| *Mondnacht*, páginas 9 y 10, limpias | 35 y 40 s (con `implicitTuplets`: 34,5 y 38,4 s) |
| *Mondnacht*, páginas 9 y 10, «foto» | 48 y 51 s (con `implicitTuplets`: 45,9 y 49,3 s) |
| Autógrafo de *An die Musik* | 75,5 s |
| Sonata al doble de tamaño (2254×1432 px) | 12,9 s (12,7 s con `implicitTuplets`) |
| Sonata a su tamaño (1127×716 px) | Falla en 2,6 s: «too low interline value of 9 pixels» |

- **Interlínea mínima.** Audiveris rechaza las páginas con menos de 11 px entre líneas del pentagrama (`ScaleBuilder`, constante `minInterline`); HOMR no. Hay que reescalarlas antes.
- **Límite de la web.** La web corta `POST /transcribe` a los 30 s (`TRANSCRIBE_TIMEOUT_MS`, `apps/web/src/api/config.ts`), la transcripción es síncrona (ADR-0016), y de los dos huecos de transcripción solo uno calcula a la vez: el otro espera el cerrojo de HOMR (ADR-0024).
- **HOMR tampoco es rápido con páginas completas.** En la máquina de desarrollo tardó entre 19,7 y 26,9 s por página de *Mondnacht*. No es comparable con r2d2, pero indica que una página completa ya se acerca a los 30 s sin Audiveris.

### 3.2. Notas

*Mondnacht*: 1272 notas en las dos páginas.

| Variante | HOMR | Audiveris | Audiveris con `implicitTuplets` |
|---|---|---|---|
| Limpia: altura y duración | 1177 (93 %) | 1011 (79 %) | 1007 (79 %) |
| Limpia: solo altura | 94 % | 90 % | 90 % |
| «Foto»: altura y duración | 1244 (98 %) | 686 (54 %) | 681 (54 %) |
| «Foto»: solo altura | 98 % | 70 % | 73 % |

HOMR acierta más en la versión «foto» que en la limpia. No se investigó por qué.

**Autógrafo de *An die Musik*** (verdad: 3 pentagramas, 23 compases, 629 notas):
- HOMR lee 1 parte y 44 compases. De 525 notas leídas, 108 coinciden en altura y duración, y 231 coinciden en altura sin mirar la duración (incluidas esas 108).
- Audiveris lee 1 parte y 19 compases. De 50 notas leídas, 14 coinciden en altura y duración, y 24 en altura.
- Ninguno sirve en este manuscrito, y Audiveris queda mucho peor.

**Sonata** (sin verdad; Audiveris con `implicitTuplets`):
- Las alturas de la mano derecha de los compases 1 a 4 coinciden entre los dos motores: 12 de 12 en cada compás.
- Audiveris lee mal la armadura de la mano izquierda en el primer sistema (compases 1 a 3): 2 sostenidos en vez de los 4 impresos. Desde el compás 4 lee 4, como HOMR en toda la página.
- Audiveris inventa un cambio de armadura a 1 sostenido en el compás 8 de la mano derecha. Por eso, en el compás 8 lee sol y re donde HOMR lee sol♯ y re♯, y en el 9, sol donde HOMR lee sol♯.

### 3.3. Compás y tresillos

| Página | Impreso | HOMR | Audiveris |
|---|---|---|---|
| *Mondnacht* | 3/8 | 3/8 | 3/8 |
| Autógrafo de *An die Musik* | ¢ | 2/2, sin símbolo | 3/4 |
| Sonata | ¢ | 3/2 | ¢ (`<time symbol="cut">`, 2/2) |

No basta con preferir siempre el compás de Audiveris.

**Tresillos en la Sonata (mano derecha).** La partitura marca el «3» solo en el compás 1.
- **HOMR:** ningún tresillo (0 `<time-modification>`). En los compases 1 a 4 lee 12 corcheas que suman 6 negras, y de ahí sale el 3/2.
- **Audiveris sin `implicitTuplets`:** tresillos en 9 de los 12 eventos del compás 1. En los compases 2 a 4 lee 9 corcheas: pierde 3 de las 12 notas.
- **Audiveris con `implicitTuplets`:**
  - en los compases 1 a 4, 12 corcheas de tresillo que suman 2/2 (87 `<time-modification>` en la página);
  - en los compases 6, 7 y 11, la voz de los tresillos también suma 2/2, pero en el 6 y el 7 la validación sigue marcando las otras voces;
  - los compases 5, 8, 9 y 10 siguen descuadrados.

**Validación de Cadenza.**
- Con la lectura de HOMR, `measure.balance` marca los compases 5, 6, 10 y 11 de la mano derecha y los 11 de la mano izquierda, que está bien: sus redondas y blancas suman 2/2 y no llenan un 3/2.
- Con la de Audiveris con `implicitTuplets`, marca los compases 5 a 10 de la mano derecha y el 8 de la izquierda, y `key.consistency` marca varios compases de la izquierda por la armadura mal leída.

**Ida y vuelta por Cadenza** de la lectura de Audiveris: no pierde los tresillos (87 → 89 `<time-modification>`), pero pierde el símbolo: exporta `<time>` 2/2 sin `symbol="cut"` ([#236](https://github.com/sebdavid3/Cadenza/issues/236)).

### 3.4. Marcas

*Mondnacht*, frente a lo impreso. Se muestran las propuestas y las bien colocadas, con la precisión entre paréntesis.

| Marca (verdad) | HOMR | Audiveris solo | Fusión, umbral 0,5 |
|---|---|---|---|
| **Limpia:** dinámicas (5) | 0 | 25 → 3 (12 %) | 23 → 3 (13 %) |
| **Limpia:** reguladores (24) | 0 | 22 → 21 (95 %) | 22 → 21 (95 %) |
| **Limpia:** staccatos (34) | 34 → 32 (94 %) | 67 → 25 (37 %) | Los de HOMR |
| **Limpia:** calderones (2) | 2 → 2 | 5 → 1 | Los de HOMR |
| **«Foto»:** dinámicas (5) | 0 | 11 → 1 (9 %) | 10 → 2 (20 %) |
| **«Foto»:** reguladores (24) | 0 | 7 → 7 (100 %) | 6 → 6 (100 %) |
| **«Foto»:** staccatos (34) | 35 → 34 (97 %) | 65 → 17 (26 %) | Los de HOMR |
| **«Foto»:** calderones (2) | 2 → 2 | 2 → 1 | Los de HOMR |

- **Otros umbrales de fusión.** Con umbral 0, las dinámicas fusionadas de la «foto» llegan a 11 → 3 (27 %); con 0,7, a 7 → 1 (14 %). En la limpia, 25 → 3 (12 %) y 22 → 3 (14 %).
- **Con `implicitTuplets`**, las dinámicas apenas cambian. En la limpia, 24 → 3 (12 %) solo y 22 → 3 (14 %) fusionadas con umbral 0,5. En la «foto», 12 → 1 (8 %) y 11 → 2 (18 %).
- **Reguladores:** Audiveris coloca bien 21 de los 24 en la página limpia, pero solo 7 en la «foto».
- **Dinámicas:** acierta 3 de las 5 impresas en la limpia, pero de sus 25 propuestas 22 no aciertan, y 20 ni siquiera caen en el compás correcto.

**Sonata.** La página tiene impresas 2 dinámicas, *pp* en los compases 1 y 5 (comprobado a ojo el 2026-10-26). Audiveris propone 5:
- *mp* en el compás 1, a 1/3 de negra del inicio, probablemente leída de la palabra «sempre» (hipótesis);
- *pp* en el compás 1;
- *p* en el compás 3;
- *pp* en el compás 5;
- *p* en el compás 8.

HOMR no propone ninguna.

**Autógrafo de *An die Musik*.** Lo impreso según OpenScore: 6 acentos, 5 dinámicas, 4 reguladores y 28 staccatos. HOMR no lee ninguna marca; Audiveris, un *sf* y 2 staccatos.

### 3.5. OCR

- **Sin idiomas.** Audiveris arranca sin idiomas de OCR («No installed OCR languages»; «The collection of supported languages is empty»).
- **Con los paquetes de Ubuntu.** Con `tesseract-ocr-eng` y `tesseract-ocr-ita` falla: «Tesseract (legacy) engine requested, but components are not present in /usr/share/tesseract-ocr/5/tessdata/eng.traineddata!!» y «Tesseract couldn't load any languages!».
- **Lo que haría falta.** Audiveris pide el motor *legacy* de Tesseract, que necesita los `tessdata` completos (`github.com/tesseract-ocr/tessdata`). No se probó.
- **Hipótesis sin comprobar:** con OCR bajarían las dinámicas falsas que salen de letras de textos, como la *mp* de «sempre».

## 4. Conclusiones

Valen para las páginas medidas; con tan pocas, son indicios, no una evaluación.

1. **Audiveris no puede sustituir a HOMR.** Lee peor las notas (79 % frente a 93 % en la página limpia de *Mondnacht*, 54 % frente a 98 % en la «foto») y confunde armaduras. Por sí solo tarda más de los 30 s que permite la web en las páginas reales.
2. **En estas páginas supera a HOMR en tres cosas**, que HOMR no da:
   - los reguladores de la página impresa limpia de *Mondnacht* (21 de 24, con un 95 % de precisión);
   - el símbolo ¢ de la Sonata (en el autógrafo en ¢ leyó 3/4);
   - los tresillos implícitos de los compases 1 a 4 de la Sonata, con `implicitTuplets` (otros compases siguen mal).
3. **No resuelve las dinámicas.** Sin OCR, solo acierta un 8–12 % de lo que propone; fusionado, un 13–20 % con umbral 0,5 y hasta un 27 % con umbral 0, sobre cinco dinámicas impresas. En la «foto» pierde la mayoría de los reguladores (coloca bien 7 de 24), y su compás no siempre es mejor que el de HOMR.
4. **Integrarlo cuesta caro:**
   - 35–51 s por página real en CPU (75 s el autógrafo), por encima de los 30 s de la web, con transcripción síncrona y un solo cálculo de HOMR a la vez;
   - una imagen de 636 MB con Java y GTK;
   - la licencia AGPL-3.0;
   - datos de OCR aparte.
5. **Decisión del plan de cierre** ([#231](https://github.com/sebdavid3/Cadenza/issues/231)): Audiveris no se integra en la entrega de noviembre de 2026.
   - Los matices se ponen a mano ([#214](https://github.com/sebdavid3/Cadenza/issues/214)).
   - El compás y los tresillos implícitos se abordan con una etapa propia después de HOMR ([#237](https://github.com/sebdavid3/Cadenza/issues/237)), que puede usar la misma idea que `TupletGenerator`.
   - La integración como fuente de propuestas, en segundo plano y con un umbral de precisión medido, queda descrita en [#262](https://github.com/sebdavid3/Cadenza/issues/262).

## 5. Cómo reproducirlo

1. **Páginas.**
   - El PDF de IMSLP #270920 se descarga a mano desde su página en IMSLP: la descarga no se pudo automatizar con `curl`. El usado tenía un sha256 que empieza por `baf437235f98d451` (solo se anotó el prefijo). Las páginas se sacan con `pdftoppm -r 300 -f 9 -l 10 -png op39.pdf mondnacht-p` (paquete `poppler-utils`).
   - La versión «foto» sale de `uv run --no-sync python docs/investigaciones/INV-0002/degradar_foto.py <carpeta>`. Con las mismas páginas de entrada, Pillow 12.3.0 y NumPy 2.5.3, reproduce byte a byte las imágenes usadas.
   - El autógrafo es el archivo de Wikimedia Commons citado arriba, renombrado a `an-die-musik-autografo.jpg`.
2. **Verdad.**
   - `lc4987640.mscx` y `lc6180725.mscx` del repositorio `OpenScore/Lieder` (carpetas `scores/Schumann,_Robert/Liederkreis,_Op.39/05_Mondnacht` y `scores/Schubert,_Franz/_/An_die_Musik,_D.547`).
   - Se exportan a MusicXML con MuseScore 3.6.2 (AppImage oficial; sin pantalla, con `xvfb-run`): `AppRun -o mondnacht.musicxml lc4987640.mscx` y `AppRun -o an-die-musik.musicxml lc6180725.mscx`.
3. **Motores.**
   - Audiveris con la imagen de [`Dockerfile.audiveris`](INV-0002/Dockerfile.audiveris) y la orden de la §2.1. Las salidas con y sin `implicitTuplets` tienen el mismo nombre, así que van en carpetas distintas (por ejemplo, `sin-implicitos/` y `con-implicitos/`), cada una con su propia copia de la verdad y de las salidas de HOMR.
   - HOMR con `HOMREngine(use_gpu=False).transcribe_musicxml(...)`.
   - Las salidas se nombran `homr-<variante>-p-<página>.musicxml` y `audiveris-<variante>-p-<página>.mxl`, con variante `mondnacht` o `mondnacht-foto`; las del autógrafo, `homr-autografo.musicxml` y `audiveris-autografo.mxl`; las de la Sonata (página al doble de tamaño), `homr-pagina-x2.musicxml`, `audiveris-x2-implicit-false.mxl` y `audiveris-x2-implicit-true.mxl`.
4. **Comparación.** Con cada conjunto en su carpeta (la de *Mondnacht*, junto a `lc4987640.mscx`), se ejecutan desde la raíz del repositorio:
   ```bash
   uv run --no-sync python docs/investigaciones/INV-0002/comparar_mondnacht.py <carpeta>
   uv run --no-sync python docs/investigaciones/INV-0002/fusion.py <carpeta>
   uv run --no-sync python docs/investigaciones/INV-0002/comparar_autografo.py <carpeta>
   uv run --no-sync python docs/investigaciones/INV-0002/comparar_sonata.py <carpeta>
   uv run --no-sync python docs/investigaciones/INV-0002/compases.py <archivos>
   ```
   Ninguno escribe en el repositorio ni en `results/`.

sha256 de las entradas usadas el 2026-10-24, para comprobar que se parte de lo mismo:

| Archivo | sha256 |
|---|---|
| `mondnacht-p-09.png` | `71593738c4beb025835f36a2abdf2bdf5935ade75d7f153eae203ac3622dfcfe` |
| `mondnacht-p-10.png` | `462988b4e6e542489902680c431a30fe809307964abd5c3e5bcb407e88c19b50` |
| `mondnacht.musicxml` | `5c64b5f6204e35b8dff0f84d77cc8440de85edb9535de28c8e3dd4e184cf05c5` |
| `lc4987640.mscx` | `51fad48cf9382c9699720355a01bc11662e3d31ab532ec8f5adbb36e03a939ee` |
| `an-die-musik.musicxml` | `7ab54477d8858a22197422b280f099fd38ed70a99e9886e1ede33ae1af4a3061` |
| `lc6180725.mscx` | `4c83578fece90e1f12ae9960db7689e6132c8f901d189d5f7571dcf51c302443` |
| `an-die-musik-autografo.jpg` | `1dc4c5c260d660bc7237c95718c30141978b94ede3375253d40f174c3519ecb4` |

Cualquier cifra se regenera antes de citarse (`CLAUDE.md` §8.4). Además, las imágenes de `pdftoppm` y el MusicXML de MuseScore pueden cambiar con otra versión de las herramientas: si los sha256 no coinciden, se parte de entradas distintas y las cifras pueden cambiar.
