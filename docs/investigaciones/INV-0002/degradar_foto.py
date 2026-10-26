"""Versión «foto» de Mondnacht: giro, desenfoque, luz desigual, ruido y JPEG (INV-0002).

Uso: python degradar_foto.py <carpeta de datos>

Lee `mondnacht-p-09.png` y `mondnacht-p-10.png` de la carpeta y escribe en ella
`mondnacht-foto-p-09.png` y `mondnacht-foto-p-10.png`. La semilla es fija.
"""

import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def main(datos: Path) -> None:
    rng = np.random.default_rng(205)
    for page in ("09", "10"):
        image = Image.open(datos / f"mondnacht-p-{page}.png").convert("L")
        image = image.rotate(1.5, resample=Image.BICUBIC, expand=True, fillcolor=255)
        image = image.filter(ImageFilter.GaussianBlur(1.8))
        pixels = np.asarray(image, dtype=np.float32)
        height, width = pixels.shape
        light = np.linspace(0.78, 1.0, width)[None, :] * np.linspace(0.9, 1.0, height)[:, None]
        pixels = pixels * light + rng.normal(0, 9, pixels.shape)
        image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=70)
        Image.open(buffer).save(datos / f"mondnacht-foto-p-{page}.png")
        print(page, image.size)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python degradar_foto.py <carpeta de datos>")
    main(Path(sys.argv[1]))
