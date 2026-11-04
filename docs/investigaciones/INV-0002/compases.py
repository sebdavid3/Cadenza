"""Compás que escribe cada salida de un motor, con su símbolo y cuántas veces (INV-0002).

Uso: python compases.py <archivo .musicxml o .mxl> [...]
"""

import re
import sys
import zipfile
from collections import Counter
from pathlib import Path


def xml_of(path: Path) -> str:
    if path.suffix == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(
                n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF")
            )
            return z.read(name).decode("utf-8")
    return path.read_text(encoding="utf-8")


def main(paths: list[Path]) -> None:
    for path in paths:
        times = Counter(
            " ".join(t.split())
            for t in re.findall(r"<time(?:\s[^>]*)?>.*?</time>", xml_of(path), re.S)
        )
        print(f"{path.name:40s} {dict(times)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Uso: python compases.py <archivo .musicxml o .mxl> [...]")
    main([Path(arg) for arg in sys.argv[1:]])
