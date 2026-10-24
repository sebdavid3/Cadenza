---
name: Cadenza
description: Partituras impresas, notación editable. Muestrario bitmap de papel, tinta y un único acento violeta.
colors:
  paper: "#f0eff2"
  ink: "#0a0a0a"
  ink-muted: "#4a4950"
  accent: "#7a2cf0"
  on-accent: "#f0eff2"
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

Cadenza se presenta como un muestrario tipográfico bitmap, en la tradición de los catálogos de Emigre, impreso sobre papel prensa: papel frío, tinta casi negra y un único acento violeta eléctrico. Todo se organiza en una retícula de filetes de tinta de grosor entero. Las cabeceras de sección son bloques de tinta invertidos y la marca se repite en el pie a varios tamaños rotulados. El grano del píxel es el material del mundo: la tipografía de display y de rótulos es bitmap, los iconos se dibujan en una rejilla de 8×8 y el escaneo de una partitura se pinta en canvas a un bit y se amplía con `image-rendering: pixelated`.

Frente al píxel está la nota: la notación musical se dibuja en vectores nítidos (la clave de sol y las cifras del compás son contornos de Noto Music, OFL, convertidos en rutas SVG). Esa tensión entre el escaneo pixelado y la notación limpia es la firma del sistema. El texto corrido usa un grotesco sobrio (Hanken Grotesk) para que la lectura larga no pague el precio del bitmap.

El violeta no es decoración: significa «te toca a ti». Marca la acción principal, el compás que el validador señala, el error, el foco del teclado, la selección y el cursor de texto. Los estados se distinguen por patrón (contorno, trama, macizo) antes que por nuevos colores. El sistema es plano: sin esquinas redondeadas, sin sombras difusas, sin degradados. Rechaza, según PRODUCT.md, el aire de startup SaaS, la intranet académica gris, la app lúdica y el pastiche de partitura antigua.

**Key Characteristics:**
- Papel, tinta y un solo acento violeta con significado de turno del usuario.
- Retícula de filetes de tinta de 3 px; nada redondeado, nada difuso.
- Display Pixelify Sans en mayúsculas a escala de cartel; rótulos Silkscreen; texto Hanken Grotesk.
- Estados por patrón: contorno, trama de puntos, bloque macizo.
- Escaneo pixelado en canvas frente a notación vectorial nítida.
- Un solo momento de movimiento por vista; con movimiento reducido, se muestra el estado final.

## Colors

Tres neutros de imprenta y un acento eléctrico que solo aparece cuando le toca actuar al usuario.

### Primary
- **Violeta Eléctrico** (accent): acción principal (botón «Entrar» relleno), la trama y el contorno del compás dudoso, el rótulo del hallazgo, la línea de lectura de la demostración, el campo de cierre de la landing, el anillo de foco, la selección de texto, la nota elegida en la partitura y el cursor. La barra de corrección no lo usa: sus estados son de tinta (pulsado, discontinuo). Contraste de 5,3:1 con el papel en ambos sentidos.

### Neutral
- **Papel Frío** (paper): fondo de toda la interfaz, relleno de los botones secundarios y del bloque legible sobre trama; también el texto sobre el violeta (on-accent, mismo valor).
- **Tinta de Imprenta** (ink): texto, filetes, cabeceras de sección invertidas, estado pulsado y hover de todos los botones, pentagrama y glifos musicales.
- **Tinta Gastada** (ink-muted): texto secundario, notas al pie, pies de figura, metadatos y el texto de los botones deshabilitados (7,8:1 sobre papel).

### Named Rules
**The Te Toca a Ti Rule.** El violeta marca únicamente lo que espera una acción o una decisión del usuario: acción principal, compás dudoso, error, foco. Nunca se usa como adorno, fondo de sección neutra o color de marca suelto.

**The Pattern Before Hue Rule.** Un estado nuevo se expresa con un patrón de la familia existente (contorno de tinta, trama de puntos, bloque macizo, filete discontinuo) antes que con un color nuevo. La paleta no crece.

**The Ink Rule Rule.** Los filetes son siempre de tinta y de grosor entero (3 px); el acento no se usa para bordes estructurales.

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

La cabecera mide 96 px de alto. Los pasos usan tres columnas (número, texto de hasta 34ch, figura). Los cortes observados son 1100 px (desaparece el lema de la cabecera), 900 px (las filas de dos o tres columnas pasan a una; el filete vertical se vuelve horizontal), 860 px y 600 px (la navegación baja a una segunda fila; el índice de pasos se reparte en dos por fila). En pantallas estrechas, una figura de partitura conserva un ancho mínimo legible (720 px) y se desplaza en horizontal, abriéndose sobre el compás señalado.

Los objetivos táctiles miden al menos 44 px (48 px en botones).

## Elevation & Depth

El sistema es plano. No hay sombras difusas ni capas tonales: la profundidad se sustituye por inversión (bloque de tinta), trama y filete. `box-shadow` se usa solo como anillo duro de grosor entero, sin desplazamiento ni desenfoque, para dibujar el doble filete de los botones y el contorno de la línea de lectura.

### Shadow Vocabulary
- **Doble filete** (`box-shadow: inset 0 0 0 3px <papel>, 0 0 0 3px <tinta>`): anillo interior de papel y exterior de tinta alrededor del botón primario; sobre el campo violeta, el anillo interior pasa a tinta.
- **Contorno de lectura** (`box-shadow: 0 0 0 2px <tinta>`): ribete de la línea de lectura violeta sobre la partitura.
- **Compás que suena** (`box-shadow: inset 0 0 0 3px <tinta>`): anillo interior del compás que suena en la vista de una sesión.
- **Nota elegida** (`box-shadow: 0 0 0 3px <papel>, 0 0 0 6px <violeta>`): aro de papel y filete violeta alrededor de la cabeza de la nota elegida, sobre una caja de papel.

### Named Rules
**The No Blur Rule.** Ninguna sombra lleva desenfoque ni desplazamiento. Si algo necesita destacar, se invierte, se trama o se enmarca.

## Shapes

Esquinas rectas en todo (0 px). La forma la dan los filetes de tinta de 3 px: bordes de botón, marcos de índice, separadores de columna y de sección. Los controles contiguos solapan su filete (margen negativo de 3 px) para que la línea nunca se duplique. Las superficies texturadas son matrices: trama de puntos de tinta (5 px) para lo secundario o no evaluado, trama de puntos violeta (7 px) para el compás dudoso. Los iconos son mapas de píxeles de 8×8 dibujados como rutas con `shape-rendering: crispEdges` y heredan el color del texto. Los signos musicales de los controles (figuras con su plica y corchetes, puntillo y alteraciones) usan una rejilla de 8×12 con el mismo tamaño de píxel: el icono se alarga hacia abajo, no se encoge.

## Components

### Buttons
Bloques rotulados en Silkscreen, rectos y de filete grueso.
- **Shape:** esquinas rectas (0 px), filete de tinta de 3 px, alto mínimo de 48 px, relleno 12 × 24 px, 700 en mayúsculas con 0.05em.
- **Primary:** relleno violeta, texto de papel y doble filete (anillo interior de papel, exterior de tinta). Uno por vista.
- **Secondary:** contorno de tinta sobre papel. Es el «Entrar» de la cabecera y el «Volver al inicio» de la 404.
- **On accent:** sobre el campo violeta, bloque de papel con doble filete de tinta.
- **Hover / Focus:** todos pasan a bloque de tinta con texto de papel en 160 ms con salida exponencial; el icono de flecha avanza 2 px. Foco con anillo violeta de 3 px separado 3 px (de papel sobre el violeta).
- **Disabled:** filete discontinuo, texto en tinta gastada, sin doble filete.
- **Compact:** el secundario a la medida del conmutador (44 px de alto, relleno 8 × 16 px, 0.875rem, sin partir el rótulo), para las barras de herramientas. Es el «Descargar MusicXML» de la barra de la partitura.

### Toggle (conmutador segmentado)
- **Style:** botones contiguos con filete de 3 px solapado, rótulo Silkscreen 700 a 0.875rem, alto de 44 px.
- **State:** pulsado = bloque de tinta macizo con texto de papel (`aria-pressed`); sin pulsar = papel.

### Section Title
Cabecera de sección como bloque de tinta invertido: display 700 en mayúsculas, texto de papel, relleno 12 × 16 px, a todo el ancho de la banda.

### Navigation
Cabecera de 96 px con filete inferior: la marca en display, el lema en rótulo (se oculta bajo 1100 px), enlaces en rótulo sin subrayado que se subrayan al pasar, y el acceso como botón secundario. En móvil, marca y acceso en la primera fila y los enlaces debajo. El índice de pasos es una fila de celdas enmarcadas con número en display; al pasar, la celda se invierte a tinta.

### Finding Label
Rótulo del hallazgo del validador: Silkscreen sobre bloque violeta macizo, relleno 4 × 8 px, anclado al borde del compás señalado y colgando sobre el pentagrama.

### Barra de la partitura
En la vista de una sesión, la figura de la notación lleva su barra en la misma franja que el pie: rótulo a la izquierda y acciones a la derecha, sobre un único filete. Si la partitura es estrecha (menos de 34rem), la barra baja a su propia franja bajo el pie. Lleva controles compactos con iconos de píxel. Debajo, en su propia franja, el transporte: «Reproducir» y «Pausa» en un mismo botón y «Detener», con botones contiguos de filete solapado (mientras suena, el botón cambia su rótulo a «Pausa» y es un bloque de tinta; no es un conmutador con `aria-pressed`, porque su acción cambia), el tempo como paso de − y + alrededor del valor, y a la derecha el compás que suena o la duración.

### Selección de notas
En la vista de una sesión, una franja propia entre el transporte y la partitura. A la izquierda, la nota elegida: dónde está en rótulo de tinta gastada («Compás 4 · Voz 1») y qué es en texto («Fa#5 · corchea»), precedidos por una muestra de su marca. Sin nada elegido, una indicación en texto pequeño. A la derecha, los pasos «Anterior», «Siguiente» y «Quitar», botones contiguos de 44 px con el filete solapado, como el transporte; «Quitar» lleva el filete discontinuo mientras no hay nada que quitar. Debajo, la leyenda de teclas: cada tecla es un bloque de tinta macizo con su rótulo o su flecha de píxel en papel. En una pantalla táctil la leyenda se oculta, y en una partitura estrecha los pasos ocupan la fila entera y «Anterior» y «Siguiente» quedan como flechas. Si la selección no se puede ofrecer, la franja lo dice en texto pequeño, y mientras se dibuja la partitura dice que la está preparando. En una pantalla táctil, los botones no se quedan en el estado de hover tras tocarlos.

### Corrección de la nota elegida
En la vista de una sesión, para quien la transcribió, una franja propia bajo la de la selección y encima de la partitura, con tres grupos rotulados en tinta gastada: «Altura» (bajar y subir un paso con flechas de píxel, bajar y subir una octava con chevrones dobles), «Alteración» (doble bemol, bemol, becuadro, sostenido y doble sostenido) y «Figura» (de semifusa a redonda y el puntillo), cada uno de botones contiguos de 44 px con el filete solapado, como el transporte. Los signos son iconos de píxel de 8×12 con nombre accesible y `title`; «Paso» y «Octava» llevan además la palabra. El valor que ya tiene la nota (su alteración, su figura y su puntillo) es el estado pulsado del conmutador, un bloque de tinta; lo que no se puede ahora (un silencio no tiene altura, una nota en el borde del registro), filete discontinuo. Debajo, en texto pequeño, la indicación (elegir una nota, qué admite un silencio) y lo que pasó con la última orden, en `aria-live`: «Guardando…» en tinta gastada y el resultado en tinta, con «Volver a aplicar» o «Recargar la sesión» como enlaces cuando hace falta; ningún color de estado. Debajo, la leyenda de teclas con los mismos bloques de tinta que la de la selección, oculta en una pantalla táctil. En una partitura estrecha (menos de 34rem) quedan los iconos solos y la franja estrecha su margen para que los ocho botones de figura quepan en una fila a 390 px. Al corregir, la partitura no se vacía: el estado nuevo se dibuja oculto encima y sustituye al anterior sin movimiento.

### Partitura: escaneo y notación
La pieza firma del sistema. La misma maqueta se dibuja dos veces: como escaneo, en canvas a un 20 % de resolución, umbralizado a un bit con los colores de papel y tinta leídos de los tokens y ampliado con `image-rendering: pixelated`; como notación, en SVG con pentagrama y barras de tinta de 3 px y glifos de Noto Music convertidos en rutas. El compás dudoso se marca con trama de puntos violeta y contorno violeta de 4 px; el compás ya corregido, con contorno de tinta de 4 px; el compás que suena, con contorno de tinta de 3 px por detrás de las notas y una banda maciza de tinta de 6 px colgada bajo su caja, fuera de ella para no tapar plicas ni notas graves (no es violeta: no pide nada); la nota elegida, con una caja de papel por detrás de su cabeza, un aro de papel y un filete violeta de 3 px (pide acción), que abre un hueco en la trama del compás dudoso y aparece sin movimiento; una nota partida en figuras ligadas se marca figura a figura, y con colores forzados la marca es un contorno con el color de selección del sistema. Con notas que elegir, la partitura toma el anillo de foco del sistema. Las dos vistas comparten proporción (1360 / 262) y se superponen exactamente.

**Movimiento:** la lectura es el único momento animado de la vista. Al entrar en pantalla, una línea violeta recorre la imagen de izquierda a derecha en 2400 ms con `steps(56, end)` (saltos de columna, como un escáner) y descubre la notación con un recorte. Con `prefers-reduced-motion` o sin soporte, se muestra directamente el estado final con el compás señalado. En la vista de una sesión, el único movimiento es el del compás que suena: su banda entra con un barrido a saltos de 240 ms (`steps(6)`); con movimiento reducido aparece sin barrido y el compás se trae a la vista sin desplazamiento suave. El resto de transiciones del sistema son cambios de color de 160 ms con `cubic-bezier(0.16, 1, 0.3, 1)`.

## Do's and Don'ts

### Do:
- **Do** reservar el violeta para la acción principal, el compás dudoso, el error y el foco, y usar un solo botón primario por vista.
- **Do** separar columnas y secciones con filetes de tinta de 3 px y solapar los filetes de controles contiguos.
- **Do** expresar estados con patrón: contorno de tinta (reposo o resuelto), trama de puntos (señalado o no evaluado), bloque macizo (pulsado, hover, cabecera) y filete discontinuo (deshabilitado).
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
- **Don't** pixelar la notación vectorial ni cargar una fuente musical completa para unos pocos glifos.
- **Don't** pedir tipografías ni recursos a servidores de terceros.
- **Don't** caer en el aire de startup SaaS, intranet académica gris, app lúdica o pastiche de partitura antigua (pergamino, caligrafía, ornamentos).
