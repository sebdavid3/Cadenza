---
name: Cadenza
description: Partituras impresas, notación editable. Muestrario bitmap de papel, tinta y un único acento violeta.
colors:
  paper: "#f0eff2"
  ink: "#0a0a0a"
  ink-muted: "#4a4950"
  accent: "#7a2cf0"
  on-accent: "#f0eff2"
  rule-soft: "#bdbcbf"
  ink-faint: "#8a898d"
  paper-raised: "#f7f6f8"
typography:
  display:
    fontFamily: "Pixelify Sans, Silkscreen, monospace"
    fontSize: "clamp(3.5rem, 10vw, 9.25rem)"
    fontWeight: 700
    lineHeight: 0.86
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Pixelify Sans, Silkscreen, monospace"
    fontSize: "clamp(1.75rem, 3.6vw, 2.5rem)"
    fontWeight: 700
    lineHeight: 1
  heading:
    fontFamily: "Pixelify Sans, Silkscreen, monospace"
    fontSize: "clamp(2rem, 4.5vw, 3rem)"
    fontWeight: 700
    lineHeight: 1
  title:
    fontFamily: "Pixelify Sans, Silkscreen, monospace"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.1
  lead:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "1.3125rem"
    fontWeight: 400
    lineHeight: 1.4
  body:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\" 1"
  small:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Silkscreen, Pixelify Sans, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "0.06em"
rounded:
  none: "0px"
spacing:
  space-1: "4px"
  space-2: "8px"
  space-3: "12px"
  space-4: "16px"
  space-5: "24px"
  space-6: "32px"
  space-7: "40px"
  space-8: "56px"
  space-9: "80px"
  gutter: "clamp(16px, 2.8vw, 40px)"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "12px 24px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "12px 24px"
    height: "48px"
  button-secondary-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  button-on-accent:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "12px 24px"
    height: "48px"
  button-on-accent-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  button-compact:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "8px 16px"
    height: "44px"
  button-disabled:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-muted}"
  toggle:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "8px 16px"
    height: "44px"
  toggle-pressed:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  section-title:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    typography: "{typography.headline}"
    padding: "12px 16px"
  finding-label:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    padding: "4px 8px"
  key-cap:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    padding: "0 4px"
    height: "24px"
  site-header:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    height: "96px"
    padding: "16px clamp(16px, 2.8vw, 40px)"
---

# Design System: Cadenza

## Overview

**Creative North Star: "El muestrario bitmap"**

Cadenza se presenta como un muestrario tipográfico bitmap, en la tradición de los catálogos de Emigre, impreso sobre papel prensa: papel frío, tinta casi negra y un único acento violeta eléctrico. Todo se organiza en una retícula de filetes de tinta de grosor entero. Las cabeceras de sección son bloques de tinta invertidos y el pie cierra con el logo. El grano del píxel es el material del mundo: la tipografía de display y de rótulos es bitmap, el logo es la palabra dibujada en una rejilla de celdas, los iconos se dibujan en una rejilla de 8×8 y el escaneo de una partitura se pinta en canvas a un bit y se amplía con `image-rendering: pixelated`.

Frente al píxel está la nota: la notación musical se dibuja en vectores nítidos (la clave de sol y las cifras del compás son contornos de Noto Music, OFL, convertidos en rutas SVG). Esa tensión entre el escaneo pixelado y la notación limpia es la firma del sistema. El texto corrido usa un grotesco sobrio (Hanken Grotesk) para que la lectura larga no pague el precio del bitmap.

El violeta no es decoración: significa «te toca a ti». Marca la acción principal, el compás que el validador señala, el error, el foco del teclado, la selección y el cursor de texto. Los estados se distinguen por patrón (contorno, trama, macizo) antes que por nuevos colores. El sistema es plano: sin esquinas redondeadas, sin sombras difusas, sin degradados. Rechaza, según PRODUCT.md, el aire de startup SaaS, la intranet académica gris, la app lúdica y el pastiche de partitura antigua.

**Key Characteristics:**
- Papel, tinta y un solo acento violeta con significado de turno del usuario.
- Retícula de filetes de tinta de 3 px; nada redondeado, nada difuso.
- Display Pixelify Sans en mayúsculas a escala de cartel; rótulos Silkscreen; texto Hanken Grotesk.
- La marca es un logo dibujado en la rejilla del píxel, no texto: la A final es un calderón cuyo punto violeta es el «te toca a ti».
- Estados por patrón: contorno, trama de puntos, bloque macizo.
- Escaneo pixelado en canvas frente a notación vectorial nítida.
- Un solo momento de movimiento por vista; con movimiento reducido, se muestra el estado final.

## Colors

Tres neutros de imprenta y un acento eléctrico que solo aparece cuando le toca actuar al usuario.

### Primary
- **Violeta Eléctrico** (accent): acción principal (botón «Entrar» relleno), la trama y el contorno del compás dudoso, el rótulo del hallazgo, la línea de lectura de la demostración, el campo de cierre de la landing, el anillo de foco, la selección de texto, la nota elegida en la partitura y el cursor; el punto del logo, el calderón de la A final (#383); en la vista de transcripción, el rótulo y la trama fina de las láminas con posibles errores, la lectura de la imagen que se transcribe y el aviso al soltar imágenes (#370). La barra de corrección no lo usa: sus estados son de tinta (pulsado, desvaído). Contraste de 5,3:1 con el papel en ambos sentidos.

### Neutral
- **Papel Frío** (paper): fondo de toda la interfaz, relleno de los botones secundarios y del bloque legible sobre trama; también el texto sobre el violeta (on-accent, mismo valor).
- **Tinta de Imprenta** (ink): texto, filetes, cabeceras de sección invertidas, estado pulsado y hover de todos los botones, pentagrama y glifos musicales.
- **Tinta Gastada** (ink-muted): texto secundario, notas al pie, pies de figura, metadatos y el texto de los botones deshabilitados (7,8:1 sobre papel).
- **Filete Suave** (rule-soft): tinta al 22 % sobre papel, sin otro tono. Solo agrupa los botones de una barra de herramientas de la mesa de corrección (#363), con 1 px alrededor del grupo y entre botón y botón.
- **Tinta Desvaída** (ink-faint): tinta al 45 % sobre papel. Lo que ahora no se puede pulsar en las barras de la mesa (#363), en lugar del filete discontinuo de cada botón.
- **Papel Claro** (paper-raised): papel con un 45 % de blanco. El pie de la partitura, donde va el transporte (#363).

### Named Rules
**The Te Toca a Ti Rule.** El violeta marca únicamente lo que espera una acción o una decisión del usuario: acción principal, compás dudoso, error, foco. Nunca se usa como adorno, fondo de sección neutra o color de marca suelto. La única excepción es el punto del logo, el único violeta fuera de las acciones, porque es el propio signo del «te toca a ti»: el calderón en que la máquina se detiene y empieza el turno del usuario. Ninguna letra del logo es violeta.

**The Pattern Before Hue Rule.** Un estado nuevo se expresa con un patrón de la familia existente (contorno de tinta, trama de puntos, bloque macizo, filete discontinuo) antes que con un color nuevo. La paleta no crece con tonos nuevos: los tres de la mesa (#363, filete suave, tinta desvaída y papel claro) son tinta rebajada sobre papel.

**The Ink Rule Rule.** Los filetes son siempre de tinta y de grosor entero (3 px); el acento no se usa para bordes estructurales. La única excepción es el filete suave de 1 px que agrupa los botones de una barra de herramientas de la mesa (#363): agrupa, no estructura, y es tinta rebajada, no otro color.

## Typography

**Display Font:** Pixelify Sans 700 (con Silkscreen, monospace)
**Body Font:** Hanken Grotesk 400 y 500 (con system-ui, sans-serif)
**Label/Mono Font:** Silkscreen 400 y 700 (con Pixelify Sans, monospace)

**Character:** Dos voces bitmap, una para gritar a escala de cartel y otra para rotular en pequeño, sobre un grotesco tranquilo que lleva el texto. Las tres se sirven desde el propio proyecto con `@fontsource`, solo el subconjunto latino; no se pide nada a servidores de terceros.

### Hierarchy
- **Display** (700, `clamp(3.5rem, 10vw, 9.25rem)`, 0.86, mayúsculas): el titular de cartel de una página. Variantes de la misma voz en la landing: el cierre a `clamp(3rem, 8vw, 7rem)`, los encabezados de columna a `clamp(2.5rem, 6vw, 4.5rem)`, los números de paso a 6rem y el código de la 404 a `clamp(6rem, 28vw, 22rem)`.
- **Headline** (700, `clamp(1.75rem, 3.6vw, 2.5rem)`, 1, mayúsculas): cabecera de sección en bloque de tinta invertido.
- **Heading** (700, `clamp(2rem, 4.5vw, 3rem)`, 1, mayúsculas): titular de páginas de sistema (404).
- **Title** (700, 1.375rem, 1.1, mayúsculas): títulos de elementos de lista (pasos).
- **Lead** (400–500, 1.3125rem, 1.4): entradillas y listas de alcance; medida de 56–60ch.
- **Body** (400, 1rem, 1.5, cifras tabulares): texto corrido; medida de 48–64ch.
- **Small** (400, 0.875rem): notas bajo acciones y secciones, en tinta gastada.
- **Label** (Silkscreen 400, 0.8125rem, 0.06em, mayúsculas): navegación, metadatos, pies de figura, rótulo del hallazgo y enlaces secundarios. Los botones y conmutadores usan la misma familia a 700, entre 0.875rem y 1rem, con 0.05em.

### Named Rules
**The Bitmap Shouts, Grotesk Reads Rule.** Pixelify Sans y Silkscreen van siempre en mayúsculas y solo en titulares, rótulos y controles; ningún párrafo se compone en bitmap.

**The Single Weight Display Rule.** El display solo existe en 700 (es el único peso cargado); la jerarquía se hace con tamaño e inversión, no con pesos.

## Layout

Retícula de bandas a todo el ancho separadas por filetes de tinta, sin contenedor centrado: el margen lateral es el `gutter` fluido (16–40 px). El espaciado avanza en pasos de 4 px (`space-1` a `space-9`); las secciones respiran con 56–80 px en vertical y los bloques internos con 24–32 px. Las columnas se separan con un filete vertical en lugar de con aire: el titular y su texto, los pasos del índice, lo probado y lo no evaluado.

La cabecera mide 96 px de alto. Los pasos usan tres columnas (número, texto de hasta 34ch, figura). Los cortes observados son 1140 px (desaparece el lema de la cabecera), 900 px (las filas de dos o tres columnas pasan a una; el filete vertical se vuelve horizontal), 860 px y 600 px (la navegación baja a una segunda fila; el índice de pasos se reparte en dos por fila). En pantallas estrechas, una figura de partitura conserva un ancho mínimo legible (720 px) y se desplaza en horizontal, abriéndose sobre el compás señalado.

Los objetivos táctiles miden al menos 44 px (48 px en botones).

**La mesa de corrección** (la vista de una sesión, #341) es la excepción a las bandas: a partir de 960 px es una aplicación del alto de la ventana, sin desplazamiento de la página, bajo una cabecera única de 64 px como mucho que sustituye a la de la aplicación (#363), y la imagen original, un divisor y la partitura se reparten el ancho; los posibles errores y el historial van en un panel a la derecha que se pliega a un raíl. Cada panel se desplaza por su lado, de modo que la foto y la nota que se corrige se ven a la vez. Bajo 960 px vuelve a una columna, con la imagen fija arriba (un 30 % del alto, y se puede ocultar), la partitura debajo y el panel al final.

**El diario de transcripción** (la vista de transcripción, #370) vuelve a las bandas. Bajo la cabecera, una barra de unos 100 px con el título de la vista y la subida, y debajo un día por banda, del más reciente al más antiguo, separadas por filetes de tinta. Cada día lleva a la izquierda un margen de `clamp(8.5rem, 13vw, 12.5rem)` cerrado por un filete vertical, con la fecha fija mientras se recorre el día, y a la derecha sus láminas en una retícula de celdas de al menos 15rem (cuatro por fila a 1440 px, cinco a 1600). Bajo 760 px la fecha encabeza el día en una línea y el botón de la barra ocupa el ancho; bajo 560 px cada lámina es una fila, con la imagen (6,5rem, en 3:4; en 3:2 si es una franja ancha) a la izquierda y sus datos al lado.

## Elevation & Depth

El sistema es plano. No hay sombras difusas ni capas tonales: la profundidad se sustituye por inversión (bloque de tinta), trama y filete. `box-shadow` se usa solo como anillo duro de grosor entero, sin desplazamiento ni desenfoque, para dibujar el doble filete de los botones y el contorno de la línea de lectura.

### Shadow Vocabulary
- **Doble filete** (`box-shadow: inset 0 0 0 3px <papel>, 0 0 0 3px <tinta>`): anillo interior de papel y exterior de tinta alrededor del botón primario; sobre el campo violeta, el anillo interior pasa a tinta.
- **Contorno de lectura** (`box-shadow: 0 0 0 2px <tinta>`): ribete de la línea de lectura violeta sobre la partitura.
- **Compás que suena** (`box-shadow: inset 0 0 0 3px <tinta>`): anillo interior del compás que suena en la vista de una sesión.
- **Compás señalado** (`box-shadow: inset 0 0 0 2px <violeta>`, sobre la trama fina; el elegido suma `0 0 0 3px <tinta>`): contorno del compás con posibles errores en la vista de una sesión (#368).
- **Lámina al pasar** (`box-shadow: 0 0 0 3px <tinta>`): dobla el filete del marco de la imagen de una lámina del diario, que entera abre la sesión (#370).
- **Nota elegida** (`box-shadow: 0 0 0 3px <papel>, 0 0 0 6px <violeta>`): aro de papel y filete violeta alrededor de la cabeza de la nota elegida, sobre una caja de papel.

### Named Rules
**The No Blur Rule.** Ninguna sombra lleva desenfoque ni desplazamiento. Si algo necesita destacar, se invierte, se trama o se enmarca.

## Shapes

Esquinas rectas en todo (0 px). La forma la dan los filetes de tinta de 3 px: bordes de botón, marcos de índice, separadores de columna y de sección. Los controles contiguos solapan su filete (margen negativo de 3 px) para que la línea nunca se duplique. Las superficies texturadas son matrices: trama de puntos de tinta (5 px) para lo secundario o no evaluado, trama de puntos violeta (7 px) para el compás dudoso de la demostración y su variante fina (puntos de 1 px de radio cada 8 px) para el de la partitura de una sesión, que se lee a través de ella (#368). Los iconos son mapas de píxeles de 8×8 dibujados como rutas con `shape-rendering: crispEdges` y heredan el color del texto. Los signos musicales de los controles (figuras con su plica y corchetes, puntillo y alteraciones) usan una rejilla de 8×12 con el mismo tamaño de píxel: el icono se alarga hacia abajo, no se encoge.

## Components

### Buttons
Bloques rotulados en Silkscreen, rectos y de filete grueso.
- **Shape:** esquinas rectas (0 px), filete de tinta de 3 px, alto mínimo de 48 px, relleno 12 × 24 px, 700 en mayúsculas con 0.05em.
- **Primary:** relleno violeta, texto de papel y doble filete (anillo interior de papel, exterior de tinta). Uno por vista.
- **Secondary:** contorno de tinta sobre papel. Es el «Entrar» de la cabecera y el «Volver al inicio» de la 404.
- **On accent:** sobre el campo violeta, bloque de papel con doble filete de tinta.
- **Hover / Focus:** todos pasan a bloque de tinta con texto de papel en 160 ms con salida exponencial; el icono de flecha avanza 2 px. Foco con anillo violeta de 3 px separado 3 px (de papel sobre el violeta).
- **Disabled:** filete discontinuo, texto en tinta gastada, sin doble filete. En las barras de herramientas de la partitura (la mesa y el resultado de la portada, #363), tinta desvaída sin filete propio.
- **Compact:** el secundario a la medida del conmutador (44 px de alto, relleno 8 × 16 px, 0.875rem, sin partir el rótulo), para las barras de herramientas. En la cabecera de una sesión mide 36 px y va a 0.75rem: «Finalizar la corrección» o «Reabrir la sesión», como primario, y dentro de «Exportar / Datos», a lo ancho del panel, «Cambiar los datos», «Descargar MusicXML», «Descargar MIDI» y «Descargar PDF» (#363, #376).

### Toggle (conmutador segmentado)
- **Style:** botones contiguos con filete de 3 px solapado, rótulo Silkscreen 700 a 0.875rem, alto de 44 px. En las barras de herramientas de la partitura (la mesa y el resultado de la portada, #363), botones sin filete propio dentro de un grupo de filete suave de 1 px, con un filete suave entre botón y botón, rótulo a 0.75rem y 36 px de alto (32 px en la paleta y el transporte; 44 px con el dedo).
- **State:** pulsado = bloque de tinta macizo con texto de papel (`aria-pressed`); sin pulsar = papel.

### Section Title
Cabecera de sección como bloque de tinta invertido: display 700 en mayúsculas, texto de papel, relleno 12 × 16 px, a todo el ancho de la banda.

### Navigation
Cabecera de 96 px con filete inferior: el logo (celdas de 4 px; 3 px por debajo de 860 px), el lema en rótulo (se oculta bajo 1140 px, donde ya no cabe en la fila con el logo), enlaces en rótulo sin subrayado que se subrayan al pasar, y el acceso como botón secundario. En móvil, marca y acceso en la primera fila y los enlaces debajo. El índice de pasos es una fila de celdas enmarcadas con número en display; al pasar, la celda se invierte a tinta.

### Marca
La marca deja de ser texto de display (#383): es el logo, la palabra CADENZA dibujada en una rejilla de celdas cuadradas de 53 × 7 (7 filas, astas de 2 celdas, trazos horizontales de 1 y 1 celda entre letras). Las dos A son de arco redondo; la primera lleva travesaño y la final lo cambia por un punto de 2 × 2 celdas a su altura, un calderón. Las letras van del color del texto (`currentColor`) y el punto en `--color-accent`, sobre papel y sobre tinta; con colores forzados, el punto pasa a `CanvasText`. Se dibuja como SVG en línea (`BrandWordmark`, con `shape-rendering: crispEdges`), decorativo dentro de un enlace que conserva su nombre accesible («Cadenza, inicio» o «Cadenza, página pública»), y mide siempre celdas de píxel enteras con `--brand-cell`, nunca en rem ni vw, para que los bordes de los píxeles no se difuminen: 4 px en la cabecera pública (212 × 28 px; 3 px por debajo de 860 px, para que una tableta de 768 px siga en una fila), y 3 px (159 × 21 px) en la de la zona privada y en la de la vista de una sesión; en la mesa estrecha (de 1100 a 1280 px), la de la sesión pasa a 2 px (106 × 14 px) para dejar sitio al título. La guía de uso (espacio libre, tamaños mínimos, variantes de color y lo que no se hace) y los SVG maestros están en `docs/marca/`.

**Pie de la portada.** El logo una sola vez, con celdas de 6 px (318 × 42 px; 4 px, 212 × 28 px, por debajo de 400 px), sobre la línea de créditos en rótulo. Sustituye al muestrario de la palabra escrita a cuatro tamaños rotulados: por decisión del responsable, sin tamaños ni rótulos. Es un adorno (`aria-hidden`): el nombre ya está en la línea de créditos.

**Favicon e iconos.** El símbolo es la A final sola, con su calderón. El favicon (`favicon.svg`, 16 px con celdas de 2 px) es de tinta y pasa a papel en modo oscuro, con el punto violeta; `favicon.ico` lleva 16, 32 y 48 px. El `apple-touch-icon` y los iconos de 192 y 512 px (también el *maskable*) son la A de papel con el punto violeta sobre una baldosa de tinta de esquinas rectas. `site.webmanifest` los reúne con `display: browser`: no se promete una aplicación instalable. Sustituyen a la corchea de píxel sobre violeta.

### Finding Label
Rótulo del hallazgo del validador: Silkscreen sobre bloque violeta macizo, relleno 4 × 8 px, anclado al borde del compás señalado y colgando sobre el pentagrama. En la partitura de una sesión lleva solo el número del compás, con relleno 1 × 4 px, para no tapar lo que hay sobre el pentagrama; el del compás elegido es de tinta (#368).

### Diario y láminas
La vista de transcripción (#370), un diario de trabajo.
- **Barra:** «Transcripciones» en display a 1,75–2,5rem y, debajo, en rótulo de tinta gastada, de quién son las sesiones («Tus sesiones» o «Todas las sesiones») y su orden. A la derecha, «Nueva transcripción», el único primario, que abre el selector de imágenes, y, en texto pequeño, que también se pueden soltar en cualquier parte (sin ratón no se dice) y lo que se admite («PNG o JPEG, de hasta 20 MB»). Al elegirlas, el formulario «Antes de transcribir» (#240) se abre en una banda bajo la barra.
- **Margen del día:** el número del día en display a `clamp(3.5rem, 6.4vw, 6rem)`, el mes y el año en rótulo de tinta gastada y, cuando toca, «Hoy» o «Ayer» en un bloque de tinta. Para el lector de pantalla, el encabezado es la fecha entera («Hoy, lunes, 9 de noviembre de 2026»).
- **Lámina de una sesión:** la imagen en un marco de tinta de 3 px (3:2), en escala de grises multiplicada sobre papel claro: una página se ve por arriba y una franja ancha (un incipit, más de 2,2 veces ancha que alta) entera y centrada. Debajo, el nombre en texto a 1,0625rem (dos líneas como mucho), que es el enlace a la sesión: toda la lámina responde al clic, y al pasar, el nombre se invierte a bloque de tinta, su flecha avanza 2 px y el marco de la imagen dobla su filete. Después, en texto pequeño de tinta gastada y separados por puntos, de quién es (para un investigador), la hora, el compositor y los instrumentos; y el estado con su rótulo (contorno; macizo de tinta si está finalizada) y las ediciones. Con posibles errores, la trama fina violeta del compás señalado (#368) va bajo la imagen multiplicada, así que solo se ve en el papel y la notación sigue en tinta, y el rótulo violeta («12 posibles errores») cuelga de la esquina inferior de la imagen sobre su filete, como el del compás en la mesa (arriba taparía el título impreso); en una lámina en fila vuelve a la línea del estado.
- **La cola**, solo mientras hay imágenes y dentro del día de hoy: una cabecera con «Cola» en un bloque de tinta, el recuento en vivo y «Limpiar terminadas», sobre un filete, y una lámina por imagen con el archivo elegido como imagen. En cola, el marco es discontinuo y la imagen se desvae; al transcribirse, pasa la lectura (ver Movimiento). Bajo el estado, en texto pequeño de tinta gastada, en qué está en el servidor (#375): «Subiendo la imagen», cuántas van delante («2 por delante», «Es la siguiente»), «Preparando la lectura» (mientras espera su turno en HOMR), «Detectando los pentagramas», «Leyendo el pentagrama 3 de 8», la segunda lectura de una página de voz y piano por su nombre («Segunda lectura, con el piano por separado: …») y «Revisando el compás y los posibles errores». Mientras lee los pentagramas, un filete de 3 px de tinta suave se llena de violeta con los ya leídos de esa lectura, a saltos y sin transición: nunca un porcentaje que no salga de lo hecho. Una imagen recuperada del servidor al volver a la vista no trae su archivo y su miniatura dice «Sin imagen»; una que se interrumpió (ya no está en el servidor y no creó su sesión) lleva el rótulo «Interrumpida» y, sin su archivo, solo se puede quitar. En la portada, la línea del avance no se anuncia: el lector de pantalla oye solo la etapa. Con error, el marco es violeta, con el rótulo rayado y el motivo en texto. Al terminar, la lámina muestra sus posibles errores y «Abrir la sesión» hasta que la sesión aparece en el listado: entonces sale de la cola y su sesión es una lámina más del día, debajo, con la misma imagen; el foco, si lo tenía, pasa a ella, y el recuento la sigue contando. Si una acción vacía la cola, el foco pasa a «Nueva transcripción». El recuento se anuncia desde una región viva que existe aunque no haya cola.
- **Soltar imágenes:** mientras se arrastran archivos sobre la ventana, la trama violeta cubre la página sobre un papel al 86 % que deja entrever el diario, con un bloque de papel con filete de tinta: «Suelta las imágenes» en display y qué se admite.
- **Vacío:** la banda de hoy se dibuja igual, con «Todavía no hay sesiones.» en display y, en texto, cómo empezar.

### Mesa de corrección
La vista de una sesión (#341, compacta desde #363). **Cabecera única:** sustituye a la de la aplicación y, en la mesa, cabe en una franja de 64 px como mucho. A la izquierda, el logo (celdas de 3 px; de 2 px entre 1100 y 1280 px) con un filete a su derecha, la vuelta a las sesiones, el título (se recorta con puntos suspensivos antes que partirse) con un resumen en rótulo pequeño debajo («En corrección · 12 ediciones», y «solo lectura» y de quién es cuando no se puede corregir) y «?», un cuadrado de 32 px que abre un panel con la entradilla (qué hacer al corregir, o por qué es de solo lectura) y todos los datos de la sesión. A la derecha, «Exportar / Datos», que abre un panel con «Cambiar los datos» y las tres descargas (MusicXML, MIDI y PDF) con sus avisos; «Finalizar la corrección» (o «Reabrir la sesión») como único primario; y, tras un filete, la cuenta y «Salir». Los paneles se abren bajo su botón, sobre la vista, con filete de tinta: no son modales, Esc los cierra y devuelve el foco, y un clic fuera o el foco que pasa a otro control también; mientras se guardan los datos o se prepara el MIDI o el PDF, «Exportar / Datos» no se cierra, para que su aviso se vea. La confirmación de finalizar y, debajo, lo que pasó al finalizar o reabrir se abren igual, bajo el botón; el aviso no intercepta los clics y uno fuera lo quita de la vista. En una columna, todos estos paneles se abren bajo la cabecera, a lo ancho. La navegación de la zona de trabajo («Transcripción» y, para un investigador, «Cuentas») queda tras «← Sesiones». Entre 960 y 1280 px se oculta el rol de la cuenta, y bajo 1100 px la marca. En una columna, la franja se reparte en filas.

**Paneles.** Antes de la imagen, un enlace «Ir a la partitura» que solo se ve con el foco, porque la imagen, su zoom y el divisor van antes en el orden del teclado:
- **Imagen original:** una cabecera de 48 px con su rótulo a la izquierda y sus controles a la derecha, sobre un filete. El zoom es un grupo de filete suave como la paleta («−», la lectura del zoom, «+», «Ancho» y «Página»); en una columna de imagen de menos de 24rem, el rótulo y la lectura del zoom quedan para el lector de pantalla. Se abre ajustada al ancho y acerca por pasos hasta el 400 %. Ctrl y la rueda acercan y alejan, y + y − con el marco enfocado. Acercada, se arrastra con la mano (cursor de agarre). En una columna, «Ocultar» y «Ver» la pliegan, y bajo 480 px la lectura del zoom desaparece.
- **Divisor:** una franja de 14 px entre filetes con una trama de puntos de tinta en el centro. Al pasar o arrastrar se invierte a bloque de tinta con la trama de papel. Se arrastra entre el 20 y el 70 % del ancho, se mueve con las flechas, Inicio y Fin (`role="separator"`) y vuelve al 25 % con doble clic; sin preferencia guardada, la imagen se abre al 25 % y la partitura se lleva el resto (#363). El navegador recuerda el reparto.
- **Panel lateral:** posibles errores e historial. Se pliega a un raíl del alto de la mesa con su nombre en vertical («Posibles errores · 3», o «Historial» en la condición no asistida, sin números del validador). Empieza plegado entre 960 y 1600 px, donde la partitura necesita el ancho, y el navegador recuerda lo elegido.

### Barra de la partitura
En la mesa, la partitura lleva encima la barra de corrección, fija mientras la partitura se desplaza por dentro con 24 px de aire alrededor del pentagrama (con un alto mínimo de 12rem; si no cabe todo, el panel entero se desplaza), y al pie el transporte, como un reproductor: una franja de 48 px en papel claro con botones de 32 px (#363); en una columna, el transporte queda fijo al pie de la pantalla, y lo que se trae a la vista se coloca bajo la imagen fija, no detrás de ella: «Reproducir» y «Pausa» en un mismo botón y «Detener», con botones contiguos de filete solapado. Mientras suena, el botón cambia su rótulo a «Pausa» y es un bloque de tinta; no es un conmutador con `aria-pressed`, porque su acción cambia. El tempo es un paso de − y + alrededor del valor, y a la derecha va el compás que suena o la duración.

### Selección de notas
En la vista de una sesión de solo lectura, una franja propia encima de la partitura; con la barra de corrección, sus pasos van en la primera fila de la barra y la nota elegida en su barra de estado (#363). A la izquierda, la nota elegida: dónde está en rótulo de tinta gastada («Compás 4 · Voz 1») y qué es en texto («Fa#5 · corchea»), precedidos por una muestra de su marca. Sin nada elegido, una indicación en texto pequeño. A la derecha, los pasos «Anterior», «Siguiente» y «Quitar», un grupo como el transporte; «Quitar» va en tinta desvaída mientras no hay nada que quitar. Debajo, la leyenda de teclas: cada tecla es un bloque de tinta macizo con su rótulo o su flecha de píxel en papel. Con la barra de corrección, la leyenda se ve solo tras «Atajos» (sigue describiendo la partitura para el lector de pantalla); en una pantalla táctil se oculta. Cada atajo parte línea en vez de ensanchar la franja (#331). En una partitura de menos de 56rem, «Anterior» y «Siguiente» quedan como flechas, y bajo 34rem los pasos ocupan la fila entera. Si la selección no se puede ofrecer, la franja lo dice en texto pequeño, y mientras se dibuja la partitura dice que la está preparando. En una pantalla táctil, los botones no se quedan en el estado de hover tras tocarlos.

### Corrección de la nota elegida
En la vista de una sesión, para quien la transcribió, una franja encima de la partitura **en dos filas y una barra de estado (#363)**, con un relleno de 6 × 16 px. **La primera fila** lleva deshacer y rehacer, siempre a la vista (con su palabra en una partitura de 56rem o más; más estrecha, el icono con su nombre accesible), las pestañas «Nota», «Compás» y «Marcas» (#341, con el patrón de pestañas de ARIA: flechas, Inicio y Fin) y «Escribir»; a la derecha, los pasos de la selección y «Atajos», que abre las dos leyendas de teclas (pulsado mientras se ven). Qué desharía y qué reharía va en el `title` y la descripción accesible de sus botones, no en una línea suelta (enmienda de ADR-0034 §4). **La segunda fila** es la paleta de la pestaña: sus grupos en una sola fila que, en la mesa, se desplaza en horizontal si no cabe. Los atajos valen sea cual sea la pestaña. Las tres pestañas siguen montadas aunque no se vean, para que lo propuesto en un desplegable sin aplicar no se pierda al cambiar. «Nota» reúne la altura, la alteración, la figura y el puntillo, insertar y borrar, y el acorde y la ligadura de prolongación. «Compás» reúne el tresillo, la clave, la armadura y el compás. «Marcas» reúne las articulaciones y el calderón, la dinámica y las ligaduras de expresión y los reguladores. Los grupos van rotulados encima, en rótulo de 10 px en tinta gastada (ADR-0030 §1): «Altura» (bajar y subir un paso con flechas de píxel, bajar y subir una octava con chevrones dobles), «Alteración» (doble bemol, bemol, becuadro, sostenido y doble sostenido), «Figura» (de semifusa a redonda y el puntillo), «Insertar antes o borrar» («+ Nota», «+ Silencio» y «Borrar» con un aspa de píxel), «Clave» (sol, fa, do 3 y do 4, en palabras) y «Armadura» (un desplegable con las quince, del filete y la altura del conmutador, pegado a «Cambiar»); los rótulos de la clave y la armadura dicen hasta qué compás llegan («Clave · compases 2 a 6»). Cada grupo es un contenedor de filete suave con sus botones dentro (32 px en la mesa), separados por un filete suave, como el transporte. En la mesa, en una partitura de menos de 72rem, «Paso», «Octava», «Borrar» y los nombres de las ligaduras quedan en su icono con su `title`. Los signos son iconos de píxel de 8×12 con nombre accesible y `title`; «Paso» y «Octava» llevan además la palabra. El valor que ya tiene la nota (su alteración, su figura y su puntillo) es el estado pulsado del conmutador, un bloque de tinta; lo que no se puede ahora (un silencio no tiene altura, una nota en el borde del registro), tinta desvaída sin filete propio. **La barra de estado**, bajo la paleta y tras un filete suave: a la izquierda, la nota elegida o, sin ninguna, una sola indicación («Elige una nota o un silencio: tócalo o usa las flechas.»), y lo que admite un silencio, un hueco o un acorde; a la derecha, lo que pasó con la última orden, en `aria-live`: «Guardando…» en tinta gastada y el resultado en tinta, con «Volver a aplicar» o «Recargar la sesión» como enlaces cuando hace falta; ningún color de estado. Tras «Atajos», las dos leyendas de teclas con los mismos bloques de tinta, en un panel con filete de tinta sobre la partitura que no la empuja y que un clic fuera cierra; ocultas en una pantalla táctil. En una partitura estrecha (menos de 34rem) quedan los iconos solos y la franja estrecha su margen; con el dedo, los botones de la paleta miden 40 × 44 px para que los ocho de figura quepan en una fila a 390 px, y si un grupo no cabe, la paleta se desplaza en horizontal, no la página; «Nota», «Silencio», los nombres de las claves y «Cambiar» se ven siempre, y «Borrar» queda en su aspa, para que cada grupo quepa en una fila. Al corregir, la partitura no se vacía: el estado nuevo se dibuja oculto encima y sustituye al anterior sin movimiento.

### Escribir con el ratón y nota fantasma
El modo «Escribir» de la barra de corrección (#350, ADR-0061). **El conmutador** «Escribir» va en la primera fila, tras las pestañas, con la forma de «Atajos»: filete suave en reposo y bloque de tinta pulsado (`aria-pressed`), y la tecla W. Mientras dura, la figura y el puntillo de la pestaña «Nota» muestran pulsada la figura con que se escribe y nunca quedan desvaídos (no envían nada), y la barra de estado dice en texto pequeño cómo se escribe, tras la nota elegida si la hay (en la mesa, en una línea recortada con puntos suspensivos y entera en su `title`). **La nota fantasma** es la única pieza violeta que sigue al puntero: pide una acción, así que es violeta (`--color-accent`), y es translúcida para no tapar la partitura (cabeza al 75 %; plica, corchetes y líneas adicionales de 2 px al 80 %; la cabeza de la blanca y la redonda, hueca con filete de 2,5 px). Se dibuja como notación vectorial, con la proporción de la cabeza de la partitura (inclinada 20°) y sin pixelar. Para insertar, una línea de inserción vertical discontinua de 3 px marca el hueco entre dos figuras. Su etiqueta es un rótulo de bloque violeta con el texto en papel, a la derecha de la cabeza: qué se escribe y cómo («Sol4 · negra», «Insertar Sol4 · negra», «Sol4 al acorde»). Cuando el clic no escribiría, la cabeza pasa a filete discontinuo y la etiqueta, a papel con filete discontinuo violeta y texto de tinta: «Espera: se está guardando» mientras se guarda otra corrección, y «Ahora no se puede escribir» con el editor parado. Es el patrón del deshabilitado de los botones grandes (filete discontinuo). El cursor es una cruz sobre la partitura. Aparece y se mueve sin transiciones, como la nota elegida.

### Panel del acceso
La columna izquierda de `/entrar` y `/registro` (#392). Es la trama de tinta de siempre (`--halftone-ink`), y un canvas encima la imprime como el retrato de un compositor en semitono: los mismos puntos cada 5 px, con el área proporcional a la sombra (radio de 2,5 px en el negro, medio paso: los puntos se tocan sin cerrar un bloque macizo), en papel y tinta leídos de los tokens. Un compositor por visita (la misma de entrar a crear la cuenta), en rotación que recuerda el navegador: Bach (Haussmann, 1748), Mozart (Krafft, 1819), Beethoven (Stieler, 1820), Chopin (Bisson, 1849) y Clara Schumann (Lenbach, 1878), de dominio público, servidos desde el proyecto como grises de 320 px y solo el de la visita. La imagen cubre el panel con los ojos centrados y a un 36 % del alto (`--portrait-eye-line`; en la franja estrecha, un 22 %, por encima del titular).
- **Titular:** el de siempre, display sobre un solo bloque de papel abajo a la izquierda, del ancho de su palabra más larga; su cuerpo se ajusta al ancho de la columna (`19cqi` como mucho) para que «Registro» quepa en las columnas estrechas. Sigue siendo el `h1`.
- **Pie de lámina:** arriba a la izquierda, en el mismo eje, un bloque de papel con el nombre en rótulo y, en texto pequeño de tinta gastada, las fechas, la técnica, el autor y el año del retrato. Aparece al terminar la impresión y se oculta bajo 860 px.
- **Movimiento:** el único momento animado de la vista. Al cargar la imagen, el retrato se imprime por bandas de filas de arriba abajo, en 1400 ms y 28 saltos, como el cabezal de una imprenta: cada salto pinta solo su banda, y lo que falta deja ver la trama de CSS. Con `prefers-reduced-motion` aparece entero.
- **Accesibilidad:** el retrato y su pie son decorativos (`aria-hidden`). Sin canvas o sin la imagen, queda la trama de CSS; con colores forzados el navegador quita la trama, el panel queda liso y el retrato no se descarga.
### Permiso de uso de los datos
El aviso breve, el texto completo y su página (#378, #397). La redacción la aprobó el responsable y vive en un solo componente (`DataUseText`), que se compone de dos maneras.
- **Aviso:** texto pequeño de tinta gastada a 52ch, sin filete ni marco. En «Tu cuenta» enlaza a la página.
- **Desplegado en el registro:** «Leer el texto completo» es un botón con el aspecto de un enlace (el mismo subrayado, 44 px de alto; con colores forzados, `LinkText`) que despliega el texto bajo el aviso, antes de la casilla, sin otra pestaña ni navegación. Va en un recuadro de filete de tinta sobre papel claro, con su propio desplazamiento y enfocable con el teclado; mide como mucho 26rem o el 60 % del alto de la ventana, y al llegar a su final el desplazamiento pasa a la página. Dentro, la versión en rótulo, y cada apartado con su título en display a 1,0625rem y un filete suave encima. «Ocultar el texto completo» lo pliega.
- **Página `/uso-de-los-datos`:** bandas a todo el ancho separadas por filetes de tinta. Una cabecera con el título en display y la versión en rótulo; después, una banda por apartado con su título en display a la izquierda, en un margen de `clamp(13rem, 24vw, 21rem)` cerrado por un filete vertical, y el texto a la derecha a 1,0625rem y 64ch como mucho. Bajo 900 px, una columna, y el filete vertical pasa a un filete suave bajo el título.

### Partitura: escaneo y notación
La pieza firma del sistema. La misma maqueta se dibuja dos veces: como escaneo, en canvas a un 20 % de resolución, umbralizado a un bit con los colores de papel y tinta leídos de los tokens y ampliado con `image-rendering: pixelated`; como notación, en SVG con pentagrama y barras de tinta de 3 px y glifos de Noto Music convertidos en rutas. El compás dudoso se marca con trama de puntos violeta y contorno violeta de 4 px (en la partitura de una sesión, con la trama fina y un contorno de 2 px, y el elegido además con un anillo exterior de tinta de 3 px, #368); el compás ya corregido, con contorno de tinta de 4 px; el compás que suena, con contorno de tinta de 3 px por detrás de las notas y una banda maciza de tinta de 6 px colgada bajo su caja, fuera de ella para no tapar plicas ni notas graves (no es violeta: no pide nada); la nota elegida, con una caja de papel por detrás de su cabeza, un aro de papel y un filete violeta de 3 px (pide acción), que abre un hueco en la trama del compás dudoso y aparece sin movimiento; el hueco de una voz (un silencio invisible que la partitura no dibuja), con la trama de puntos de tinta de lo secundario en el sitio de su silencio, por detrás de las notas y sin ningún signo; una nota partida en figuras ligadas se marca figura a figura, y con colores forzados la marca es un contorno con el color de selección del sistema, y la del compás señalado, un contorno con el color del texto (más grueso y por fuera en el elegido) y un filete en su rótulo (#368). Con notas que elegir, la partitura toma el anillo de foco del sistema. Las dos vistas comparten proporción (1360 / 262) y se superponen exactamente.

**Movimiento:** la lectura es el único momento animado de la vista. Al entrar en pantalla, una línea violeta recorre la imagen de izquierda a derecha en 2400 ms con `steps(56, end)` (saltos de columna, como un escáner) y descubre la notación con un recorte. Con `prefers-reduced-motion` o sin soporte, se muestra directamente el estado final con el compás señalado. En la vista de una sesión, el único movimiento es el del compás que suena: su banda entra con un barrido a saltos de 240 ms (`steps(6)`); con movimiento reducido aparece sin barrido y el compás se trae a la vista sin desplazamiento suave. En la vista de transcripción (#370), el único movimiento es la lectura sobre la lámina de la imagen que HOMR está transcribiendo: una línea violeta de 4 px con el contorno de lectura recorre la imagen en 2400 ms con `steps(48, end)`, en bucle, y deja atrás lo leído (lo que falta queda bajo un velo de papel); el rótulo «Transcribiendo» no se anima en la lámina. Con movimiento reducido, la línea queda quieta al 40 %. El resto de transiciones del sistema son cambios de color de 160 ms con `cubic-bezier(0.16, 1, 0.3, 1)`.

## Do's and Don'ts

### Do:
- **Do** reservar el violeta para la acción principal, el compás dudoso, el error y el foco, y usar un solo botón primario por vista (un panel que pide confirmar o guardar lleva el suyo mientras está abierto).
- **Do** separar columnas y secciones con filetes de tinta de 3 px y solapar los filetes de controles contiguos (en las barras de herramientas de la partitura, un filete suave de 1 px entre botón y botón).
- **Do** expresar estados con patrón: contorno de tinta (reposo o resuelto), trama de puntos (señalado o no evaluado), bloque macizo (pulsado, hover, cabecera) y filete discontinuo (deshabilitado; en las barras de la mesa, tinta desvaída).
- **Do** componer titulares y rótulos en Pixelify Sans o Silkscreen en mayúsculas, y el texto corrido en Hanken Grotesk con medidas de 48–64ch.
- **Do** dibujar la notación musical como vectores nítidos y reservar el pixelado para lo que representa una imagen escaneada.
- **Do** dibujar los iconos en la rejilla de 8×8 de los iconos de píxel, con `currentColor`.
- **Do** limitar cada vista a un momento animado y dar siempre un estado final completo con movimiento reducido.
- **Do** servir las tipografías desde el proyecto con `@fontsource`.

### Don't:
- **Don't** redondear esquinas ni usar sombras con desenfoque o desplazamiento.
- **Don't** introducir un segundo color de acento, degradados o colores de estado (verde, rojo, ámbar); el error también es violeta.
- **Don't** usar filetes estructurales de color o de grosor fraccionario; el contorno violeta queda para marcar el compás dudoso.
- **Don't** componer párrafos en tipografía bitmap ni usar un display de sistema.
- **Don't** escribir la marca con una fuente ni darle al logo celdas fraccionarias (rem, vw): se usa `BrandWordmark` con celdas de píxel enteras, y su dibujo no se retoca.
- **Don't** pixelar la notación vectorial ni cargar una fuente musical completa para unos pocos glifos.
- **Don't** pedir tipografías ni recursos a servidores de terceros.
- **Don't** caer en el aire de startup SaaS, intranet académica gris, app lúdica o pastiche de partitura antigua (pergamino, caligrafía, ornamentos).
