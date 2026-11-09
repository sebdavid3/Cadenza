"""`scripts/puertas.py`: las puertas de la CI en local mientras la de GitHub está bloqueada (#349).

Las pruebas no ejecutan ninguna puerta: el script recibe un ejecutor que devuelve el código y la
salida que pide cada caso.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.puertas import (
    Gate,
    Result,
    build_plan,
    main,
    pr_line,
    pytest_counts,
    run_gates,
)

REPO = Path(__file__).resolve().parents[2]


def _names(plan: Sequence[Gate]) -> list[str]:
    return [gate.name for gate in plan]


def test_by_default_it_runs_python_and_web_like_the_ci() -> None:
    plan = build_plan(web=True, docker=False)

    assert _names(plan) == [
        "ruff",
        "black",
        "mypy",
        "pytest",
        "npm lint",
        "npm format:check",
        "npm test",
        "npm build",
    ]
    by_name = {gate.name: gate for gate in plan}
    # Nunca `uv sync`: desinstalaría HOMR (CLAUDE.md §7).
    for name in ("ruff", "black", "mypy", "pytest"):
        assert by_name[name].command[:3] == ("uv", "run", "--no-sync")
    assert by_name["mypy"].command[3:] == ("mypy", "packages", "apps")
    assert by_name["npm build"].cwd == REPO / "apps" / "web"


def test_without_web_and_with_docker() -> None:
    assert _names(build_plan(web=False, docker=False)) == ["ruff", "black", "mypy", "pytest"]
    assert _names(build_plan(web=False, docker=True))[-2:] == ["docker api", "docker web"]


def test_every_gate_runs_even_when_one_fails() -> None:
    calls: list[str] = []

    def runner(gate: Gate) -> tuple[int, str]:
        calls.append(gate.name)
        return (1, "") if gate.name == "black" else (0, "")

    results = run_gates(build_plan(web=False, docker=False), runner)

    assert calls == ["ruff", "black", "mypy", "pytest"]
    assert [result.ok for result in results] == [True, False, True, True]


def test_the_pytest_counts_come_from_its_last_line() -> None:
    output = "....\n2169 passed, 5 skipped, 36 warnings in 181.64s (0:03:01)\n"

    assert pytest_counts(output) == "2169 passed, 5 skipped"
    assert pytest_counts("1 failed, 3 passed in 2.0s") == "1 failed, 3 passed"
    assert pytest_counts("no hay resumen") is None


def test_the_pr_line_names_the_commit_and_every_gate() -> None:
    results = [
        Result("ruff", ok=True, seconds=1.0, output=""),
        Result("pytest", ok=True, seconds=90.0, output="2169 passed, 5 skipped in 90s"),
        Result("npm test", ok=True, seconds=30.0, output=""),
    ]

    line = pr_line(results, commit="354b8b3", dirty=False)

    assert line == (
        "Puertas locales en verde sobre 354b8b3 (`scripts/puertas.py`): ruff, "
        "pytest (2169 passed, 5 skipped), npm test."
    )
    assert "sin comitear" in pr_line(results, commit="354b8b3", dirty=True)
    failed = [Result("mypy", ok=False, seconds=1.0, output="")]
    assert pr_line(failed, commit="354b8b3", dirty=False).startswith("Puertas locales en rojo")


def test_main_fails_if_one_gate_fails_and_explains_what_is_not_covered(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CADENZA_TEST_POSTGRES_URL", raising=False)

    def runner(gate: Gate) -> tuple[int, str]:
        return (1, "") if gate.name == "mypy" else (0, "")

    code = main(["--sin-web"], runner=runner, homr_installed=lambda: False)

    out = capsys.readouterr().out
    assert code == 1
    assert "FALLA  mypy" in out
    assert "PostgreSQL" in out and "CADENZA_TEST_POSTGRES_URL" in out
    assert "HOMR" in out


def test_main_passes_when_every_gate_passes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CADENZA_TEST_POSTGRES_URL", "postgresql+psycopg2://postgres@localhost/x")

    code = main(["--sin-web"], runner=lambda gate: (0, ""), homr_installed=lambda: True)

    out = capsys.readouterr().out
    assert code == 0
    assert "Puertas locales en verde" in out
    assert "PostgreSQL" not in out


def test_the_web_gates_need_the_installed_dependencies(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls: list[str] = []

    def runner(gate: Gate) -> tuple[int, str]:
        calls.append(gate.name)
        return 0, ""

    code = main(
        [],
        runner=runner,
        homr_installed=lambda: True,
        web_dir=tmp_path,  # sin node_modules
    )

    assert code == 1
    assert not any(name.startswith("npm") for name in calls)
    assert "npm ci" in capsys.readouterr().out
