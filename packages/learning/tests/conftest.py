"""Redirige a un directorio temporal la escritura de los experimentos (#95).

Los módulos de `ml/experiments` escriben en su constante `RESULTS_DIR`. Los tests
de este paquete los ejecutan, así que aquí se sustituye esa constante en todos
ellos antes de cada test: las salidas reales de `results/` quedan intactas.

`ml.cli` no tiene esa constante: sus rutas por defecto son literales bajo
`results/`, de modo que los tests deben pasarle siempre rutas explícitas.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

EXPERIMENTS_DIR = Path(__file__).resolve().parents[3] / "ml" / "experiments"


def _experiment_modules() -> list[ModuleType]:
    names = ["ml.experiments.common", "ml.experiments.corpus"]
    names += sorted(f"ml.experiments.{path.stem}" for path in EXPERIMENTS_DIR.glob("exp_*.py"))
    return [importlib.import_module(name) for name in names]


@pytest.fixture(autouse=True)
def _redirect_experiment_results(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dos pasadas: primero se importan todos con el `RESULTS_DIR` real y después
    # se parchean. Así cada módulo vuelve a su valor real al terminar el test y
    # las constantes derivadas de solo lectura siguen apuntando a `results/`.
    modules = _experiment_modules()
    target = tmp_path_factory.mktemp("results")
    for module in modules:
        if hasattr(module, "RESULTS_DIR"):
            monkeypatch.setattr(module, "RESULTS_DIR", target)
