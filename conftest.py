"""Configuración global de pytest.

Ejecutar la suite no debe tocar `results/`, que guarda las salidas reales de los
experimentos de la tesis. Esta guarda falla si algún test crea, borra o modifica
un archivo de ese directorio (#95).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _snapshot(directory: Path) -> dict[str, tuple[int, int]]:
    if not directory.is_dir():
        return {}
    return {
        path.name: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in directory.iterdir()
        if path.is_file()
    }


@pytest.fixture(scope="session", autouse=True)
def _results_dir_is_untouched() -> Iterator[None]:
    before = _snapshot(RESULTS_DIR)
    yield
    after = _snapshot(RESULTS_DIR)
    changed = sorted(
        name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
    )
    assert not changed, "La suite de tests modificó results/: " + ", ".join(changed)
