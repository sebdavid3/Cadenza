# ADR-0057: El banco de partituras del estudio: imágenes y verdades regenerables desde un manifiesto

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0010, ADR-0031, ADR-0032, ADR-0044 y ADR-0056, CLAUDE.md §8 y §9). El banco lo aprobó el responsable el 2026-11-01 (#247).
- **Relacionado:** [ADR-0056](ADR-0056-conjunto-de-referencia-del-compas-tresillos-armaduras-y-voz-con-piano.md), [protocolo §2.3](../experimentos/protocolo_medicion_esfuerzo.md), [#244](https://github.com/sebdavid3/Cadenza/issues/244), [#247](https://github.com/sebdavid3/Cadenza/issues/247), [#250](https://github.com/sebdavid3/Cadenza/issues/250), [#239](https://github.com/sebdavid3/Cadenza/issues/239)

---

## Contexto

El estudio con participantes (#253) corrige cinco partituras: TS-01 a TS-04 y la del calentamiento (protocolo §2.3 y §5.2). Cada una necesita una imagen, su verdad en MusicXML (para la fidelidad residual de `exp_10`, #250) y saber qué errores de HOMR tiene y si la barra los corrige. El responsable aprobó el banco: dos íncipits de PrIMuS y tres fragmentos de *Winterreise* (Breitkopf, IMSLP #60822, dominio público) con su verdad de OpenScore Lieder (CC0), ya en `data/reference/`.

- El issue pide las imágenes fuera de `data/` y `results/`, sin versionar, y un manifiesto versionado con sus sha256.
- TS-02 y TS-03 son dos sistemas de una página: empiezan a mitad de la pieza y no imprimen la indicación de compás. Su verdad debe llevar el compás, la armadura y la clave que rigen allí.
- El MEI de PrIMuS no escribe la alteración de la armadura (`pname="f"` sin `accid.ges` con un sostenido): leído tal cual, TS-01 tendría Fa natural donde suena Fa sostenido (lo mismo que resolvió `cadenza.learning.primus` en #255).
- OpenScore codifica algo distinto de lo grabado en un caso (TS-03, c. 2: una ligadura de prolongación como ligadura de expresión).
- music21 escribe en cada MusicXML la fecha y unos identificadores de parte al azar: la misma verdad tendría cada día otro sha256.
- `music21` solo se importa en `packages/interchange` (CLAUDE.md §10.3).

## Decisión

1. **Manifiesto y carpeta de salida.** `docs/experimentos/banco_de_partituras.json` fija, por partitura, el origen, la licencia, la página del PDF y la impresa, el recorte en píxeles a 300 ppp, los compases de la verdad (ordinales, con la anacrusa como compás 1, y los de la fuente), las erratas y los sha256 de cada fuente y de cada salida. `scripts/build_study_bank.py` lo lee, comprueba el sha256 de cada fuente (falla si falta o no es la misma), escribe la imagen y la verdad en `banco_estudio/` (en `.gitignore`; el script se niega a escribir en `data/` o en `results/`) y compara sus sha256 con el manifiesto. `--update-manifest` los reescribe; `--sources-root` lee las fuentes de otro checkout.
2. **Imágenes.** La página del PDF con `pdftoppm -r 300` (poppler 24.04.0, como ADR-0056) y, si hay recorte, el recorte con Pillow a todo el ancho; los íncipits de PrIMuS, su PNG tal cual (renders de Verovio, no escaneos).
3. **Verdad de un fragmento de OpenScore.** `cadenza.interchange.musicxml_excerpt(path, first, last)` escribe con music21 los compases ordinales `first` a `last`, numerados desde 1 como los de HOMR, con la clave, la armadura y el compás que rigen al principio insertados en su primer compás si no están allí (un cambio de clave a mitad de compás rige después). Lo demás queda como en la fuente: letra, ornamentos, textos y cambios de clave a mitad de compás, aunque la vista no los edite; `exp_10` decide qué compara (#250). Una ligadura que cruza el borde del recorte queda con un solo extremo, como se ve en la página (en el banco, solo la ligadura de expresión del último compás de TS-02; las de prolongación tienen sus dos extremos). Los identificadores de las partes se numeran en orden (P1, P2… y P1-I1…), y los compases se eligen por posición: si la fuente no los numera en orden, falla.
4. **Verdad de un íncipit de PrIMuS.** El MEI leído con `read_score`, la altura que suena de cada nota tomada del `.semantic` (`with_sounding_pitches`) y escrito con el exportador del sistema.
5. **Erratas.** Lo que la fuente codifica distinto de lo grabado se corrige después, sobre el MusicXML, con una errata del manifiesto que dice qué, dónde y por qué; si no encuentra lo que corrige, el script falla. Hoy solo hay una clase, `ligadura_de_expresion_a_prolongacion`.
6. **Salida estable.** Sin la fecha de codificación y con las partes numeradas P1, P2… y sus instrumentos P1-I1…: dos ejecuciones dan los mismos bytes.

## Consecuencias

- Cualquiera con las fuentes de `data/` regenera el banco y comprueba que es el mismo; otra versión de `pdftoppm`, Pillow, music21 o converter21 puede dar otros bytes y el script lo dice.
- La verdad de TS-02 a TS-04 trae lo que la vista no edita (letra, ornamentos, cambios de clave a mitad de compás). Leída con `read_score`, el pentagrama de la voz queda detrás del piano, porque la importación pone primero las partes de un `StaffGroup` (`_group_parts`), y la sesión de HOMR, en otro orden: #250 tiene que emparejar los pentagramas antes de medir (protocolo §2.3).
- **TS-04 son los cc. 8-13** (sistemas 3 y 4 de la p. 72), decisión del responsable del 2026-11-02: con la página entera, HOMR mezcla los pentagramas del sistema 2 y la vista no puede corregirlo. Son 6 compases, no los 12 que preveía el protocolo.
- Lo que HOMR lee de cada partitura y lo que la barra corrige, medido contra la API local, está en el protocolo §2.3.

### Riesgos, con el issue que los resuelve antes del congelado

Decisión del responsable del 2026-11-02; la revisión del banco se repite cuando entren.

- **Huecos de una voz (silencios invisibles)** que HOMR deja en TS-03 y la vista no deja elegir ni borrar: notas desplazadas, un compás lleno que no se arregla y la voz inferior del c. 2 imposible de escribir. [#317](https://github.com/sebdavid3/Cadenza/issues/317).
- **Avisos falsos de `accidental.repeated`** en TS-02 (y en TS-04). [#318](https://github.com/sebdavid3/Cadenza/issues/318).
- **El orden y la agrupación de los pentagramas** de voz y piano (voz y mano derecha en una parte en TS-02 y TS-03; la voz debajo en TS-04). [#239](https://github.com/sebdavid3/Cadenza/issues/239).
- **El compás**, que HOMR no lee en los recortes que no lo imprimen y lee mal en TS-01. [#237](https://github.com/sebdavid3/Cadenza/issues/237).
- **Límite documentado:** la ligadura de TS-02 (c. 3, mano derecha) une dos notas que HOMR pone en voces distintas, y `SetTie` no liga entre voces (422). No se corrige.
- **Trabajo de #250:** el SER de la fidelidad residual tiene que emparejar los pentagramas de la verdad y de la sesión (en otro orden, por lo dicho arriba) y normalizar el orden de las notas de un acorde y el número de voz; sin eso, una partitura corregida en todo lo que se ve da un SER lejos de 0. [#250](https://github.com/sebdavid3/Cadenza/issues/250).

## Alternativas consideradas

- **Escribir la verdad con el exportador del sistema (`read_score` y `score_ir_to_musicxml`) también para OpenScore.** Descartada: el `ScoreIR` pone cada clave al principio de su compás, así que el primer compás de TS-02 en la mano izquierda empezaría en clave de sol, y la verdad dejaría de ser lo grabado.
- **Recortar con `Score.measures()` de music21 sin más.** Descartada: no pone en el primer compás la clave, la armadura ni el compás que rigen.
- **Leer el MEI de PrIMuS tal cual.** Descartada: da Fa natural en TS-01.
- **Versionar las imágenes y las verdades.** Descartada: el issue pide no hacerlo, y el PDF y las verdades ya están fuera del repositorio.
