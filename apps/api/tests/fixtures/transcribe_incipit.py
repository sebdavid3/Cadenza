"""Transcribe con HOMR el íncipit propio dentro de la imagen de la API (D57, #192).

La CI lo ejecuta en el contenedor como lo arranca el despliegue: sin root, sin capacidades y con
el sistema de archivos de solo lectura salvo `/tmp`, el HOME del usuario y un volumen de
artefactos. Si HOMR no pudiera escribir lo que necesita (por ejemplo, si tuviera que descargar
sus pesos), fallaría aquí. Compara las alturas para saber que transcribió de verdad: si cambian
HOMR o sus pesos, puede que haya que actualizarlas.

`incipit.png` es `incipit.musicxml` dibujado con Verovio 6.3.0 (`pageWidth` 2100, `scale` 40,
`breaks` none) y pasado a PNG con CairoSVG 2.9.1 a escala 1,4, como se generó PrIMuS.
"""

import re
import sys
from pathlib import Path

from cadenza.omr.adapters.homr import HOMREngine

# Las alturas del íncipit, sin alteraciones: Fa La Do La | Si♭ La Sol Fa Sol | La Do Fa Mi | Fa.
EXPECTED_STEPS = list("FACABAGFGACFEF")


def main() -> int:
    image = Path(__file__).with_name("incipit.png")
    musicxml = HOMREngine(use_gpu=False).transcribe_musicxml(image)
    steps = re.findall(r"<step>([A-G])</step>", musicxml)
    print(f"Alturas transcritas: {' '.join(steps)}")
    if steps != EXPECTED_STEPS:
        print(
            f"Se esperaban: {' '.join(EXPECTED_STEPS)}. HOMR transcribió, pero leyó otra cosa: "
            "¿cambiaron HOMR o sus pesos?",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
