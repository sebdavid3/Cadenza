# Retratos del panel del acceso

Las cinco imágenes de esta carpeta son el retrato en gris que el panel de `/entrar` y `/registro` imprime en semitono (#392, `AccessPanel.tsx`). Se descargaron de Wikimedia Commons el 2026-11-10, como miniaturas de 960 px (la de Clara Schumann, a su tamaño original), y todas son de dominio público: obras bidimensionales cuyo autor murió hace más de cien años.

| Archivo              | Retrato                                                      | Fuente                                                                                                      |
| -------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| `bach.jpg`           | Johann Sebastian Bach, óleo de Elias Gottlob Haussmann, 1748 | [File:Johann Sebastian Bach.jpg](https://commons.wikimedia.org/wiki/File:Johann_Sebastian_Bach.jpg)         |
| `mozart.jpg`         | Wolfgang Amadeus Mozart, óleo de Barbara Krafft, 1819        | [File:Wolfgang-amadeus-mozart 1.jpg](https://commons.wikimedia.org/wiki/File:Wolfgang-amadeus-mozart_1.jpg) |
| `beethoven.jpg`      | Ludwig van Beethoven, óleo de Joseph Karl Stieler, 1820      | [File:Beethoven.jpg](https://commons.wikimedia.org/wiki/File:Beethoven.jpg)                                 |
| `chopin.jpg`         | Frédéric Chopin, daguerrotipo de Louis-Auguste Bisson, 1849  | [File:Frederic Chopin photo.jpeg](https://commons.wikimedia.org/wiki/File:Frederic_Chopin_photo.jpeg)       |
| `clara-schumann.jpg` | Clara Schumann, pastel de Franz von Lenbach, 1878            | [File:Clara Schumann 1878.jpg](https://commons.wikimedia.org/wiki/File:Clara_Schumann_1878.jpg)             |

## Cómo se prepararon

Con Pillow, sobre cada descarga:

1. Recorte de la cabeza y el busto, a todo el ancho y desde arriba: el 78 % del alto (Bach), del 6 al 86 % (Mozart), del 6 % del ancho a la derecha y el 78 % del alto (Beethoven), el 74 % (Chopin) y el 80 % (Clara Schumann).
2. Paso a gris (luminancia) y `ImageOps.autocontrast` con un 1 % de corte en cada extremo.
3. Reducción a 320 px de ancho (Lanczos) y una curva de gamma que aclara los medios tonos: 0,85 (Bach), 0,9 (Mozart y Beethoven), 1 (Chopin) y 0,8 (Clara Schumann).
4. JPEG en gris de calidad 78 (de 13 a 30 KB cada uno).

El panel solo descarga el retrato de la visita. Dónde están los ojos de cada uno (para recortarlo sin cortar la cara) está en `../portraits.ts`.
