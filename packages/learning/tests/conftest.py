"""Redirige a un directorio temporal la escritura de los experimentos (#95).

Los módulos de `ml/experiments` escriben en su constante `RESULTS_DIR`. Los tests
de este paquete los ejecutan, así que aquí se sustituye esa constante en todos
ellos antes de cada test: las salidas reales de `results/` quedan intactas.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

EXPERIMENTS_DIR = Path(__file__).resolve().parents[3] / "ml" / "experiments"


def _experiment_modules() -> list[str]:
    names = ["ml.experiments.common", "ml.experiments.corpus", "ml.cli"]
    names += sorted(f"ml.experiments.{path.stem}" for path in EXPERIMENTS_DIR.glob("exp_*.py"))
    return names


@pytest.fixture(autouse=True)
def _redirect_experiment_results(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path_factory.mktemp("results")
    for name in _experiment_modules():
        # Se importan todos de antemano: un módulo cargado por primera vez dentro
        # de un test enlazaría el `RESULTS_DIR` real.
        module = importlib.import_module(name)
        if hasattr(module, "RESULTS_DIR"):
            monkeypatch.setattr(module, "RESULTS_DIR", target)
