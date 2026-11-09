---
version: 1
slug: "pages-transcription-transcriptionpage-tsx-31f7e01c"
primary_target: "apps/web/src/pages/transcription/TranscriptionPage.tsx"
related_targets: ["apps/web/src/pages/transcription/SessionsDiary.tsx","apps/web/src/pages/transcription/transcription.css"]
---

# Vista de transcripción (`/transcripcion`)

## Alcance y modo
La portada de la zona privada: el archivo de las sesiones de una persona (todas, para un investigador), con la subida de imágenes y la cola. Modo: Operate. Hereda el mundo de DESIGN.md (muestrario bitmap); el rediseño (#370) cambia la composición, no el mundo.

## Visitante, tarea y contenido
- Visitante: transcriptores que vuelven a ver y retomar sus transcripciones, y que de vez en cuando suben un lote; investigadores que auditan las de todos.
- Tarea principal, según el responsable (2026-11-09): ver las transcripciones hechas. Subir es secundario y la cola solo importa mientras hay imágenes.
- Contenido real por sesión: imagen, nombre (título, archivo o identificador), hora de creación, compositor, instrumentos, estado (transcrita, en corrección, finalizada, fallida), posibles errores, ediciones y, para un investigador, de quién es. La API pagina de 20 en 20 y no da totales.
- Restricciones: contrato de la API v1 sin cambios; la portada (#277) comparte la zona de subida y los rótulos de estado.

## Dirección elegida
«Diario de trabajo», elegido por el responsable el 2026-11-09 entre tres composiciones (diario, catálogo de incipits, «sigue donde lo dejaste»). Momento memorable: la fecha a escala de cartel en el margen de cada día y la lectura violeta que recorre la lámina de la imagen que HOMR está leyendo.

## Sin decidir
- Si el diario debería poder filtrarse por estado (la API no filtra; filtrar solo lo cargado mentiría).

## Direction contract
THESIS: el archivo de sesiones como diario de trabajo: cada día es una banda con su fecha en el margen y sus láminas, la más reciente primero. Rechaza la cabecera de subida a media pantalla, la columna de cola vacía y la tabla de filas iguales.

OWN-WORLD: el de DESIGN.md sin añadidos: papel, tinta y el violeta solo para lo que pide la mano (primario, posibles errores, error, foco, lectura). Fecha en Pixelify Sans a 6rem, rótulos en Silkscreen, texto en Hanken Grotesk. Filetes de tinta de 3 px entre bandas y en el margen; láminas con la imagen en un marco de tinta, en escala de grises multiplicada sobre papel; la trama fina violeta y el rótulo violeta colgado de la esquina marcan las que tienen posibles errores.

STORY: la persona reconoce sus partituras por su imagen y por el día en que las hizo, ve de un vistazo cuáles piden revisión y entra en una con un clic. Si trae imágenes, las suelta en cualquier parte o pulsa «Nueva transcripción»; las ve avanzar en el día de hoy y, al terminar, cada una sale de la cola y pasa a ser una lámina más del día, justo debajo, con su misma imagen.

FIRST VIEWPORT: cabecera de la aplicación (96 px). Barra de unos 100 px: «TRANSCRIPCIONES» en display a 40 px y «Tus sesiones · la más reciente primero» debajo; a la derecha, la indicación de soltar y «Nueva transcripción» como único primario. Debajo, la banda de hoy: margen de 12,5rem con «09» a 6rem, «NOV 2026» y el bloque «HOY», un filete vertical, y cuatro láminas por fila a 1440 px. Asoma la banda de ayer.

FORM: diario por días, quinto de mi lista de siete (archivo de láminas, catálogo de incipits, lista agrupada por estado, maestro-detalle, diario por días, sigue donde lo dejaste, tablero por estado), repartido por la tirada. Seed b4458454. Interacción firma: la lectura violeta a saltos de columna (2,4 s, steps(48)) sobre la lámina que se transcribe, que deja atrás la parte leída; con movimiento reducido, quieta. Toda la página recibe las imágenes soltadas, con un aviso de trama violeta mientras se arrastran.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
