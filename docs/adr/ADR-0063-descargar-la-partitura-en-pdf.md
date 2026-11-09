# ADR-0063: Descargar la partitura en PDF, dibujada en el navegador

- **Estado:** Aceptado
- **Fecha:** 2026-11-09
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0006, ADR-0010, ADR-0021, ADR-0026 y ADR-0041, CLAUDE.md §9), a petición del responsable del 2026-11-09 (#376)
- **Relacionado:** [ADR-0021](ADR-0021-visualizacion-de-la-transcripcion-y-marcado-de-hallazgos.md), [ADR-0026](ADR-0026-reproduccion-de-la-partitura-en-el-navegador.md), [ADR-0032](ADR-0032-varias-voces-huecos-y-plicas.md), [ADR-0041](ADR-0041-titulo-compositor-e-instrumentos-de-la-sesion.md), [#376](https://github.com/sebdavid3/Cadenza/issues/376), [#189](https://github.com/sebdavid3/Cadenza/issues/189), [#363](https://github.com/sebdavid3/Cadenza/issues/363)

---

## Contexto

La vista de una sesión ofrece en «Exportar / Datos» dos descargas: el MusicXML del estado que se ve (`GET /sessions/{id}/export`, el mismo que dibuja OSMD) y el MIDI (#189, que se pide al pulsarlo). El responsable pidió el 2026-11-09 poder bajar también la partitura en PDF, para imprimirla o compartirla con quien no tiene un editor de partituras: la partitura actual, con las correcciones aplicadas, y con el título y el compositor si los hay.

Hechos comprobados el 2026-11-09 sobre `dev` (`251c0ab`):

- **El MusicXML ya lleva todo lo que el PDF necesita:** el estado materializado con las correcciones, el título (`work-title`) y el compositor (`creator type="composer"`) de la sesión (ADR-0041) y el nombre de cada parte. Al cambiar los datos, la vista vuelve a pedir el MusicXML del mismo estado.
- **El servidor no tiene con qué grabar una partitura.** music21 escribe PDF a través de LilyPond o MuseScore, que no están en la imagen de la API; Verovio daría SVG, pero pasarlo a PDF pide cairo u otra biblioteca nativa. Cualquiera de las dos añade binarios a la imagen y un formato nuevo a `GET /export`, en un contrato congelado que hoy regeneran otros dos PR (#375 y el permiso de los datos).
- **El navegador ya graba la partitura:** OSMD la dibuja en SVG (ADR-0021) y se carga solo en la vista de una sesión. OSMD sabe maquetar en páginas (`pageFormat: "A4_P"`, una SVG por página) y dibujar el título, el compositor y los nombres de las partes.
- **svg2pdf.js no lee el alfa de un hexadecimal.** VexFlow pinta las claves que OSMD deja invisibles con `#12345600` y los silencios invisibles (los huecos de una voz, ADR-0032) con `#00000000`; en el primer PDF de «Letzte Hoffnung, cc. 6-13» salían una clave azul y varias claves de fa que la vista no enseña. Acepta, en cambio, `rgba(...)`, `transparent` y `none`.
- **Las fuentes estándar del PDF solo escriben WinAnsi** (Latin-1 y 27 caracteres más de cp1252: š, ž, Œ, –, ’, €…), lo que cubre el español y el alemán. Con una letra fuera («ř» de Dvořák), jsPDF escribía la línea entera letra a letra, separadas, y se salía de la hoja.

## Decisión

### 1. El PDF se dibuja en el navegador, del mismo MusicXML

«Descargar PDF», en «Exportar / Datos» tras «Descargar MusicXML» y «Descargar MIDI», dibuja en el navegador el MusicXML del estado que se ve, el que baja «Descargar MusicXML»: con las correcciones aplicadas y los datos de la sesión. No cambia la API ni el contrato v1. Si el MusicXML aún no ha llegado, espera al que se está pidiendo sin pedirlo otra vez.

### 2. Cómo se dibuja

- **Una instancia propia de OSMD**, fuera de la vista (en un contenedor fuera de la pantalla, oculto y que no se lee), con el backend SVG, `pageFormat: "A4_P"`, el título, el subtítulo, el compositor y el letrista, los nombres de las partes y los números de compás, en negro. Lee el MusicXML con el mismo `parseMusicXml` que la vista. Al terminar, o si falla, se borra y se quita de la página.
- **El tamaño de la notación no depende de la ventana:** el contenedor mide 1200 px, que OSMD toma como 120 unidades (el espacio entre dos líneas) en los 210 mm del A4: un pentagrama de 7 mm, como en una partitura impresa. Márgenes de 8 unidades (14 mm); los de OSMD (5, casi 9 mm) quedan justos para muchas impresoras.
- **Los textos en Helvetica**, la fuente estándar del PDF que no hay que incrustar y el grotesco más cercano al Hanken Grotesk de la vista (DESIGN.md). Lo que no cabe en WinAnsi pierde su diacrítico (ř → r, č → c) o, si ni así cabe (otro alfabeto), pasa a «?». Solo en lo que se dibuja: las propiedades del PDF conservan el nombre, porque jsPDF las escribe en UTF-16 cuando no caben en PDFDocEncoding.
- **En vectores:** jsPDF crea un A4 vertical en puntos y svg2pdf.js pasa cada página SVG de OSMD a una del PDF, a página completa. Antes, un color con alfa en `fill` o `stroke` pasa a `none` si es 0 y a `rgba(...)` si no: lo invisible sigue invisible.
- **Las propiedades del PDF:** el título y el compositor que lee OSMD (`title`, `author`), si los hay, y `creator: "Cadenza"`.
- **El nombre**, como las otras descargas: `cadenza-<8 primeros del id>.pdf`, de tipo `application/pdf`.

### 3. El botón se comporta como el del MIDI

«Descargar MIDI» y «Descargar PDF» son el mismo componente (una descarga que solo se prepara al pulsarla): mientras se prepara, el botón lo dice («Preparando el PDF…»), no lo vuelve a preparar y «Exportar / Datos» no se cierra con un clic fuera; si falla, lo dice y lo anuncia, y pulsarlo otra vez lo vuelve a intentar; si llega más de 5 s después del clic o cuando la vista ya no está, no se descarga solo («El PDF ya está listo. Pulsa «Descargar PDF» para guardarlo.»). La vista guarda el último PDF con su MusicXML: pedirlo otra vez con el mismo (tras el aviso de listo, o mientras se prepara) da el mismo sin dibujarlo, y un MusicXML distinto (otro estado u otros datos) da uno nuevo. Un fallo no se guarda.

### 4. Lo que se carga y las dependencias

OSMD, jsPDF y svg2pdf.js se importan al pedir el PDF: la vista no los paga si no se usa (en la compilación, jsPDF va en un trozo de 399 kB y svg2pdf.js en uno de 86 kB; los opcionales de jsPDF, html2canvas, DOMPurify y canvg, quedan en trozos que el PDF no carga). Dos dependencias nuevas, con versión exacta: `jspdf` 4.2.1 y `svg2pdf.js` 2.8.1, las dos MIT (la 2.9.0 de svg2pdf.js era del 2026-10-29, demasiado reciente).

## Consecuencias

### Positivas

- Un PDF legible y vectorial de lo que se ve, sin tocar la API, el contrato ni la imagen del servidor, y sin entrar en la cola de los PR que regeneran `openapi.json` y `types.ts`.
- La misma notación que la vista (OSMD), con las correcciones y los datos que ya lleva el MusicXML.

### Negativas y límites

- **El PDF se dibuja en el hilo principal:** mientras OSMD maqueta, la página no responde. Las sesiones del estudio (fragmentos de una página) tardan menos de un segundo; una partitura de 56 compases y tres pentagramas tardó 5,5 s en desarrollo, y entonces el botón dice que ya está listo y el segundo clic lo guarda.
- **Los textos dibujados solo en WinAnsi:** una letra latina de fuera pierde su diacrítico («Dvořák» se dibuja «Dvorák») y un título o un compositor en otro alfabeto (griego, cirílico, CJK) sale con «?»; incrustar una fuente con más alfabetos queda fuera.
- **La maquetación es la de OSMD en A4**, no la de la página original: los saltos de sistema y de página los decide OSMD.
- **No hay PDF desde la API:** un cliente que no sea la web no lo puede pedir.

## Alternativas consideradas

- **Generarlo en el servidor** (music21 con LilyPond o MuseScore, o Verovio con una biblioteca para pasar SVG a PDF): binarios nuevos en la imagen, un formato nuevo en `GET /export` con el contrato congelado y otra maquetación distinta de la que se ve. Descartada.
- **Imprimir con el diálogo del navegador** (una hoja de estilos de impresión y «Guardar como PDF»): sin dependencias, pero no baja un archivo, depende del navegador (en el móvil es irregular) e imprimiría la vista con sus marcas o necesitaría otra página para la partitura sola. Descartada.
- **Una imagen de la partitura en un PDF** (pasar el SVG a un `canvas`): pierde los vectores, pesa más y se lee peor al ampliar o imprimir. Descartada.
