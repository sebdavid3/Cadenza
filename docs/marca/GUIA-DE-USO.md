# Cadenza: guía de uso del logo

## 1. El logo

**Idea.** La A final de CADENZA cambia el travesaño por un punto a su misma altura y se convierte en un calderón: la
pausa en la que la orquesta se detiene y empieza la cadenza del solista. En Cadenza, es el momento en que la máquina
se detiene y te toca a ti. El punto es el único píxel violeta, con la misma regla del «te toca a ti» de la interfaz.

**Construcción.** Es un dibujo sobre una rejilla de celdas cuadradas, no un texto escrito con una fuente. Cada letra
mide 7 filas de alto, con astas de 2 celdas y trazos horizontales de 1. Entre letras hay 1 celda. La palabra mide
53 × 7 celdas. Las dos A tienen el mismo arco redondo: la primera lleva travesaño y la última, el punto
de 2 × 2 celdas.

**Versiones.**

| Versión | Cuándo | Archivo |
|---|---|---|
| Palabra (principal) | Cabecera, documentos, portada de la tesis, README | `svg/cadenza-palabra-*.svg` |
| Símbolo (la A sola) | Favicon, icono de aplicación, avatar | `svg/cadenza-simbolo-*.svg`, `svg/cadenza-favicon.svg` |
| Apilado | Formatos cuadrados: póster, acreditación, redes | `svg/cadenza-apilado-*.svg` |

Cada versión tiene cuatro variantes de color: `color`, `invertido`, `negro` y `blanco` (ver §4).

## 2. Espacio libre

Alrededor del logo se deja libre, como mínimo, **el doble del lado del punto**, es decir, 4 celdas, por los cuatro
lados. Esa distancia crece y decrece con el logo. Los SVG de la palabra ya llevan 2 celdas de margen; añade el resto
al maquetar.

## 3. Tamaño mínimo y nitidez

El logo es un bitmap, así que en pantalla se ve nítido cuando cada celda mide un número entero de píxeles.

| Versión | Mínimo en pantalla | Tamaños nítidos | Mínimo impreso |
|---|---|---|---|
| Palabra | 114 px de ancho (celda de 2 px) | El archivo mide 57 celdas de ancho: 114, 171, 228, 285… px | 20 mm de ancho |
| Símbolo | 16 px (`cadenza-favicon.svg`) | 16, 32, 48, 64 px con el favicon | 5 mm |
| Apilado | 228 px de ancho | Múltiplos de 57 px de ancho | 25 mm de ancho |

Un tamaño intermedio no rompe el logo, pero difumina los bordes de los píxeles. En la web conviene fijar uno de los
tamaños nítidos. La versión invertida no se adelgaza para compensar la irradiación: rompería la rejilla y, a estos
tamaños, el efecto apenas se nota.

## 4. Color

| Nombre | HEX | RGB | CMYK (aproximado) | Pantone |
|---|---|---|---|---|
| Tinta | `#0a0a0a` | 10 10 10 | 0 0 0 96 | Negro de proceso |
| Papel | `#f0eff2` | 240 239 242 | 1 1 0 5 | Papel blanco sin tinta |
| Violeta | `#7a2cf0` | 122 44 240 | 49 82 0 6 | Sin equivalente exacto: elegirlo con una guía física |

El CMYK sale de una conversión directa de RGB y es solo un punto de partida. Para imprimir, hay que pedir una prueba.

**El violeta solo va en el punto.** Ninguna letra es violeta y el logo nunca se pinta entero de violeta.

**Contraste (WCAG):** tinta sobre papel, 17,28:1; violeta sobre papel, 5,32:1; violeta sobre blanco, 6,09:1;
violeta sobre tinta, 3,25:1, por encima del 3:1 exigido a los gráficos.

**Combinaciones aprobadas:**

- `color` (tinta y punto violeta) sobre papel o blanco.
- `invertido` (papel y punto violeta) sobre tinta o fondos oscuros.
- `negro` o `blanco`, a una tinta, sobre fotos, sobre otros colores y **sobre violeta**, donde el punto desaparecería.

## 5. Tipografía de acompañamiento

Son las fuentes de la web, todas con licencia SIL Open Font License:

- Pixelify Sans, para títulos en mayúsculas.
- Silkscreen, para rótulos.
- Hanken Grotesk, para el texto corrido.

La palabra CADENZA no se escribe con ninguna de ellas: se usa siempre el dibujo.

## 6. Lo que no se hace

- Escribir CADENZA con una fuente bitmap en lugar de usar el archivo.
- Volver a la A en pirámide de la primera ronda: parecía una nave de *Space Invaders*.
- Mover el punto, cambiarle el tamaño, redondearlo o devolverle el travesaño a la A final.
- Pintar letras de violeta o el punto de otro color, salvo en las versiones a una tinta.
- Redondear las esquinas de los píxeles o de la baldosa del icono, aunque el sistema operativo la recorte después.
- Estirar el logo, girarlo o añadirle sombras, contornos, degradados o efectos.
- Separar el símbolo de la palabra en el apilado o cambiar sus proporciones.

## 7. Archivos

Dentro del repositorio de Cadenza (#383):

```text
docs/marca/
  GUIA-DE-USO.md   esta guía
  svg/             maestros vectoriales: palabra, símbolo y apilado × color, invertido, negro y
                   blanco; favicon de 16 px que cambia a papel en modo oscuro; icono de aplicación
apps/web/public/   favicon.ico (16, 32 y 48 px), favicon.svg, apple-touch-icon.png, icon-192.png,
                   icon-512.png, maskable-512.png y site.webmanifest: se sirven desde la raíz del
                   sitio y van enlazados en apps/web/index.html
apps/web/src/components/
  BrandWordmark.tsx    la palabra como SVG en línea, con las rutas de svg/cadenza-palabra-*.svg en
                       unidades de celda (viewBox 0 0 53 7, sin el margen de los maestros)
  brand-wordmark.css   su tamaño en celdas (`--brand-cell`, en píxeles enteros) y el punto violeta,
                       que con colores forzados pasa a CanvasText
```

La web usa la palabra en la cabecera pública (celda de 4 px, y de 3 px por debajo de 860 px), en la de la zona
privada y en la de la vista de una sesión (3 px; en la sesión, 2 px entre 1100 y 1280 px de ancho) y, una sola vez,
en el pie de la portada (6 px, y 4 px por debajo de 400 px). El símbolo solo aparece en el favicon y los iconos.
`DESIGN.md` describe la marca dentro del sistema visual.

Fuera del repositorio, en el kit que se entregó al responsable (`cadenza-logo-kit.zip`), quedan los PNG de
`png/`, los `favicon-16/32/48.png` sueltos (van dentro de `favicon.ico`), las fuentes SVG de los iconos
(`web/_fuentes/`), el fragmento `head-snippet.html` y el tablero de presentación (`tablero/`).

## 8. Entrega: pruebas y pendientes

**Pruebas hechas:**

- Auditoría de los SVG con la skill: sin texto vivo, rasters, filtros ni degradados.
- Hoja de pruebas: escalera de tamaños, prueba de píxel a 16, 32 y 48 px, una tinta, invertido, desenfoque, espejo,
  giro y contextos.
- Comprobación de que cada PNG y cada icono tienen solo tres colores, es decir, ningún píxel difuminado.
- Cálculo de los contrastes de la tabla.

**Pendientes:**

- Búsqueda profesional de marca antes de cualquier registro.
- Elegir el Pantone del violeta con una guía física.

**Integrado en `apps/web` (#383):** el favicon, los iconos y el manifiesto, y la palabra en las tres cabeceras y
en el pie, en lugar de la corchea del favicon y del nombre escrito en Pixelify Sans (ver §7).
