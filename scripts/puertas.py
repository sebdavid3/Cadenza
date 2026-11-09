"""Las puertas de calidad en local: lo mismo que la CI, mientras la de GitHub está bloqueada (#349).

Desde el 2026-11-08, GitHub Actions no arranca por un cobro pendiente de la cuenta. Por decisión
del responsable, se fusiona con estas puertas en verde, la revisión independiente hecha y una
nota en el PR, que este script deja lista para pegar. Desde la raíz del repositorio:

    uv run --no-sync python scripts/puertas.py             # Python y web, como la CI
    uv run --no-sync python scripts/puertas.py --sin-web   # solo Python
    uv run --no-sync python scripts/puertas.py --docker    # y además las imágenes de Docker

Nunca `uv sync` a secas: desinstalaría HOMR (`CLAUDE.md` §7). Pasa todas las puertas aunque
falle una, para verlas todas de una vez, y dice lo que en local no se cubre.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web"
_UV = ("uv", "run", "--no-sync")
_PYTEST_PART = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed)\b")


@dataclass(frozen=True)
class Gate:
    """Una puerta: su nombre, la orden y la carpeta donde se ejecuta."""

    name: str
    command: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class Result:
    name: str
    ok: bool
    seconds: float
    output: str


Runner = Callable[[Gate], tuple[int, str]]


def build_plan(*, web: bool, docker: bool, web_dir: Path = WEB) -> list[Gate]:
    """Las puertas en el orden de la CI (`.github/workflows/ci.yml`)."""

    plan = [
        Gate("ruff", (*_UV, "ruff", "check", "."), REPO),
        Gate("black", (*_UV, "black", "--check", "."), REPO),
        Gate("mypy", (*_UV, "mypy", "packages", "apps"), REPO),
        Gate("pytest", (*_UV, "pytest"), REPO),
    ]
    if web:
        plan += [
            Gate(f"npm {script}", ("npm", "run", script), web_dir)
            for script in ("lint", "format:check", "test", "build")
        ]
    if docker:
        plan += [
            Gate("docker api", ("docker", "build", "-t", "cadenza-api:local", "."), REPO),
            Gate(
                "docker web",
                ("docker", "build", "-f", "Dockerfile.web", "-t", "cadenza-web:local", "."),
                REPO,
            ),
        ]
    return plan


def run_live(gate: Gate) -> tuple[int, str]:
    """Ejecuta la puerta mostrando su salida mientras corre, y la devuelve."""

    executable = shutil.which(gate.command[0])
    if executable is None:
        message = f"no se encuentra `{gate.command[0]}` en el PATH"
        print(message)
        return 127, message
    lines: list[str] = []
    with subprocess.Popen(
        [executable, *gate.command[1:]],
        cwd=gate.cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            lines.append(line)
    return process.returncode, "".join(lines)


def run_gates(plan: Sequence[Gate], runner: Runner) -> list[Result]:
    """Todas las puertas, aunque falle alguna."""

    results = []
    for gate in plan:
        print(f"\n=== {gate.name}: {' '.join(gate.command)}", flush=True)
        start = time.monotonic()
        code, output = runner(gate)
        results.append(Result(gate.name, code == 0, time.monotonic() - start, output))
    return results


def pytest_counts(output: str) -> str | None:
    """«2169 passed, 5 skipped» de la última línea de resumen de pytest (sin los avisos)."""

    for line in reversed(output.splitlines()):
        parts = _PYTEST_PART.findall(line)
        if parts:
            return ", ".join(f"{count} {kind}" for count, kind in parts)
    return None


def pr_line(results: Sequence[Result], *, commit: str, dirty: bool) -> str:
    """La línea para el PR: el commit y cada puerta, con el recuento de pytest."""

    names = []
    for result in results:
        counts = pytest_counts(result.output) if result.name == "pytest" else None
        names.append(f"{result.name} ({counts})" if counts else result.name)
    state = "en verde" if all(result.ok for result in results) else "en rojo"
    where = f"{commit}, con cambios sin comitear" if dirty else commit
    return f"Puertas locales {state} sobre {where} (`scripts/puertas.py`): {', '.join(names)}."


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    return done.stdout.strip()


def _homr_installed() -> bool:
    return importlib.util.find_spec("homr") is not None


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner = run_live,
    homr_installed: Callable[[], bool] = _homr_installed,
    web_dir: Path = WEB,
) -> int:
    parser = argparse.ArgumentParser(
        description="Las puertas de calidad de la CI, en local (#349)."
    )
    parser.add_argument("--sin-web", action="store_true", help="Solo las puertas de Python")
    parser.add_argument(
        "--docker", action="store_true", help="Construir también las imágenes de la API y la web"
    )
    args = parser.parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        # Vite y pytest escriben caracteres que la consola de Windows no siempre sabe mostrar.
        reconfigure(errors="replace")

    web = not args.sin_web
    plan = build_plan(web=web, docker=args.docker, web_dir=web_dir)
    skipped: list[Result] = []
    if web and not (web_dir / "node_modules").is_dir():
        message = f"faltan las dependencias de la web: ejecuta `npm ci` en {web_dir}"
        skipped = [
            Result(gate.name, ok=False, seconds=0.0, output=message)
            for gate in plan
            if gate.name.startswith("npm ")
        ]
        plan = [gate for gate in plan if not gate.name.startswith("npm ")]
    results = run_gates(plan, runner) + skipped

    print("\n=== Resumen")
    for result in results:
        mark = "OK    " if result.ok else "FALLA "
        print(f"{mark} {result.name} ({result.seconds:.0f} s)")
        if not result.ok and result.output and result in skipped:
            print(f"       {result.output}")

    notes = []
    if not os.environ.get("CADENZA_TEST_POSTGRES_URL"):
        notes.append(
            "Las pruebas de PostgreSQL se omiten: la CI las pasa contra un PostgreSQL 16; "
            "aquí hace falta CADENZA_TEST_POSTGRES_URL."
        )
    if not homr_installed():
        notes.append(
            "HOMR no está instalado: se omiten las pruebas del motor real (ver el README; "
            "nunca `uv sync` a secas)."
        )
    if not args.docker:
        notes.append("Las imágenes de Docker no se construyen sin --docker.")
    if notes:
        print("\nLo que no cubren estas puertas:")
        for note in notes:
            print(f"- {note}")

    commit = _git("rev-parse", "--short", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    print("\nPara el PR:")
    print(pr_line(results, commit=commit, dirty=dirty))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
