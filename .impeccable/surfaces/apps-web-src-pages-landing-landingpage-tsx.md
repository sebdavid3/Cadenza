---
version: 1
slug: "apps-web-src-pages-landing-landingpage-tsx"
primary_target: "apps/web/src/pages/landing/LandingPage.tsx"
related_targets: []
---

# Landing pública (`/`)

## Alcance y modo
Página pública de Cadenza. Modo: Persuade. Primera superficie del mundo visual: define el sistema que heredan el acceso y la vista de transcripción.

## Visitante, acción y prueba
- Visitante: archivos, bibliotecas y músicos que podrían pedir una cuenta al equipo; también quien ya tiene cuenta.
- Acción: «Entrar» (lleva a `/entrar`). No hay registro: se dice que las cuentas las crea el equipo del proyecto.
- Prueba: el mecanismo a la vista (imagen pixelada que se resuelve en notación, compás dudoso señalado) con un incipit sintético rotulado como ilustración, y el enlace al repositorio público. Sin cifras, testimonios ni logos.
- Restricciones: solo partituras impresas y monofónicas (PrIMuS); nada de manuscritos ni polifonía densa. Ningún enlace a la vista de edición.

## Dirección elegida
Muestrario bitmap (tipo Emigre), adoptado por el usuario el 2026-10-22 tras ver un sketch; paleta violeta eléctrico elegida en una comparativa de nueve opciones. Momento memorable: la lectura que barre el incipit de izquierda a derecha y convierte los píxeles del escaneo en notación nítida, y la trama violeta que cae sobre el compás que no cuadra.

Escena física: personas de archivo, biblioteca o música trabajando de día en un escritorio, a veces por lotes largos; por eso fondo claro de papel. Sin modo oscuro en esta tanda.

## Sin decidir
- Modo oscuro.
- Si la demostración de la landing usará más adelante una transcripción real exportada en lugar del incipit sintético.

## Direction contract
THESIS: «De píxel a nota». La página es un muestrario tipográfico bitmap en el que el escaneo pixelado de un incipit se resuelve en notación nítida y el compás dudoso queda tramado en violeta. Rechaza la página de herramienta con titular, captura de la app y tres tarjetas.

OWN-WORLD: papel #f0eff2, tinta #0a0a0a y un único acento, violeta eléctrico #7a2cf0, que significa «te toca a ti» (acción principal, compás dudoso, error). Trama de puntos y matriz como superficies. Pixelify Sans para el display a escala de cartel, Silkscreen para rótulos y Hanken Grotesk para el texto. Filetes de tinta de 3 px, sin sombras difusas ni esquinas redondeadas; botones como bloques de doble filete; estados por patrón (contorno, trama, macizo, rayado).

STORY: el visitante entiende que su partitura impresa se vuelve notación editable, que la máquina propone y señala y que él decide. Lo cree porque lo ve ocurrir. Entra si tiene cuenta o sabe que el equipo la crea.

FIRST VIEWPORT: cabecera de 96 px (CADENZA en bitmap, lema, navegación y «Entrar» en contorno). Fila de titular: «DE PÍXEL A NOTA.» a unos 150 px a la izquierda y, a la derecha tras un filete, el texto, «Entrar» en violeta y «Ver el código». Banda a todo el ancho con el incipit sintético a gran escala, el conmutador Imagen/Notación y la lectura animada. Debajo asoman los cuatro pasos.

FORM: muestrario bitmap de Emigre (catálogo `emigre-bitmap-specimen`), challenger declinado en la segunda mano y adoptado por el usuario; no estaba en mi lista ordenada. Seed f362da48, re-roll 1. Interacción firma: la lectura que revela la notación y trama el compás 3, y el conmutador honesto Imagen/Notación; con `prefers-reduced-motion`, estado final sin animación.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
