"""`scripts/puertas.py`: las puertas de la CI en local mientras la de GitHub está bloqueada (#349).

Las pruebas no ejecutan ninguna puerta: el script recibe un ejecutor, un `git` y las
comprobaciones del entorno que pide cada caso. Viven aquí, y no en `scripts/`, para que mypy
estricto (`mypy packages apps`) compruebe también el script.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from scripts.puertas import (
    WEB,
    Gate,
    Git,
    Result,
    Runner,
    build_plan,
    main,
    pr_line,
    pytest_counts,
    run_gates,
    run_live,
)

REPO = Path(__file__).resolve().parents[3]


def _names(plan: Sequence[Gate]) -> list[str]:
    return [gate.name for gate in plan]


def _git(commits: Sequence[str] = ("354b8b3",), status: str = "") -> Git:
    """Un `git` falso: `rev-parse` da los commits en orden (el último se repite)."""
    pending = list(commits)

    def git(*args: str) -> str:
        if args[0] == "rev-parse":
            return pending.pop(0) if len(pending) > 1 else pending[0]
        return status

    return git


def _ok(gate: Gate) -> tuple[int, str]:
    return 0, ""


def _main(
    argv: Sequence[str],
    *,
    runner: Runner = _ok,
    homr_installed: Callable[[], bool] = lambda: True,
    node_major: Callable[[], int | None] = lambda: 24,
    git: Git | None = None,
    web_dir: Path = WEB,
) -> int:
    return main(
        argv,
        runner=runner,
        homr_installed=homr_installed,
        node_major=node_major,
        git=git or _git(),
        web_dir=web_dir,
    )


# --- El plan -----------------------------------------------------------------------------------


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
    assert by_name["pytest"].command[3:] == ("pytest", "-rs")
    assert by_name["npm test"].command == ("npm", "run", "test", "--", "--maxWorkers=2")
    assert by_name["npm build"].cwd == REPO / "apps" / "web"
    assert by_name["pytest"].env == {}


def test_with_postgres_its_tests_are_required_like_in_the_ci() -> None:
    plan = build_plan(web=False, docker=False, postgres=True)

    assert {gate.name: gate for gate in plan}["pytest"].env == {"CADENZA_REQUIRE_POSTGRES": "1"}


def test_docker_runs_the_whole_docker_job_of_the_ci() -> None:
    plan = build_plan(web=False, docker=True)
    docker = {gate.name: gate for gate in plan[4:]}

    assert list(docker) == [
        "docker api",
        "docker api: íncipit sin root",
        "docker web",
        "docker copias",
        "docker copias: pg_dump",
        "docker copias: ayuda",
        "compose",
        "compose con copias",
    ]
    assert "VITE_REGISTRATION_ENABLED=true" in docker["docker web"].command
    run = docker["docker api: íncipit sin root"].command
    assert {"--read-only", "--cap-drop", "no-new-privileges:true"} <= set(run)
    assert "transcribe_incipit.py" in run[-1]
    compose_env = docker["compose"].env
    assert set(compose_env) == {
        "CADENZA_POSTGRES_PASSWORD",
        "CADENZA_AUTH_SECRET_KEY",
        "CADENZA_PUBLIC_ORIGIN",
    }
    assert len(compose_env["CADENZA_AUTH_SECRET_KEY"]) == 64


# --- Ejecutar ----------------------------------------------------------------------------------


def test_every_gate_runs_even_when_one_fails() -> None:
    calls: list[str] = []

    def runner(gate: Gate) -> tuple[int, str]:
        calls.append(gate.name)
        return (1, "") if gate.name == "black" else (0, "")

    results = run_gates(build_plan(web=False, docker=False), runner)

    assert calls == ["ruff", "black", "mypy", "pytest"]
    assert [result.ok for result in results] == [True, False, True, True]


def test_run_live_returns_the_code_and_the_output_in_utf8(tmp_path: Path) -> None:
    gate = Gate(
        "python",
        (sys.executable, "-c", "print('modificó'); import sys; sys.exit(3)"),
        tmp_path,
    )

    code, output = run_live(gate)

    assert code == 3
    assert "modificó" in output


def test_run_live_reports_a_missing_program(tmp_path: Path) -> None:
    code, output = run_live(Gate("nada", ("no-existe-este-programa-349",), tmp_path))

    assert code == 127
    assert "no-existe-este-programa-349" in output


# --- La línea para el PR -----------------------------------------------------------------------


def test_the_pytest_counts_come_from_its_last_line() -> None:
    output = "....\n2169 passed, 5 skipped, 36 warnings in 181.64s (0:03:01)\n"

    assert pytest_counts(output) == "2169 passed, 5 skipped"
    assert pytest_counts("1 failed, 3 passed in 2.0s") == "1 failed, 3 passed"
    assert pytest_counts("no hay resumen") is None


def test_the_pr_line_names_the_commit_every_gate_and_what_failed() -> None:
    results = [
        Result("ruff", ok=True, seconds=1.0, output=""),
        Result("pytest", ok=True, seconds=90.0, output="2169 passed, 5 skipped in 90s"),
        Result("npm test", ok=True, seconds=30.0, output=""),
    ]

    assert pr_line(results, commit="354b8b3", dirty=False) == (
        "Puertas locales en verde sobre 354b8b3 (`scripts/puertas.py`): ruff, "
        "pytest (2169 passed, 5 skipped), npm test."
    )
    assert "sin comitear" in pr_line(results, commit="354b8b3", dirty=True)
    failed = [*results, Result("mypy", ok=False, seconds=1.0, output="")]
    line = pr_line(failed, commit="354b8b3", dirty=False)
    assert line.startswith("Puertas locales en rojo")
    assert "mypy (FALLA)" in line


def test_a_partial_run_does_not_look_like_the_ci() -> None:
    results = [Result("ruff", ok=True, seconds=1.0, output="")]

    line = pr_line(results, commit="354b8b3", dirty=False, uncovered=["web (--sin-web)"])

    assert line.startswith("Puertas locales en verde, parciales")
    assert line.endswith("Sin cubrir: web (--sin-web).")


# --- main --------------------------------------------------------------------------------------


def test_main_fails_if_one_gate_fails_and_says_what_is_not_covered(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CADENZA_TEST_POSTGRES_URL", raising=False)

    def runner(gate: Gate) -> tuple[int, str]:
        return (1, "") if gate.name == "mypy" else (0, "")

    code = _main(["--sin-web"], runner=runner, homr_installed=lambda: False)

    out = capsys.readouterr().out
    assert code == 1
    assert "FALLA  mypy" in out
    assert "CADENZA_TEST_POSTGRES_URL" in out and "HOMR" in out
    assert "Sin cubrir: web (--sin-web); imágenes de Docker (sin --docker); PostgreSQL" in out


def test_main_passes_when_every_gate_passes_and_nothing_is_left_out(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CADENZA_TEST_POSTGRES_URL", "postgresql+psycopg2://postgres@localhost/x")
    (tmp_path / "node_modules").mkdir()
    calls: list[Gate] = []

    def runner(gate: Gate) -> tuple[int, str]:
        calls.append(gate)
        return 0, ""

    code = _main(["--docker"], runner=runner, web_dir=tmp_path)

    out = capsys.readouterr().out
    assert code == 0
    assert "Puertas locales en verde sobre 354b8b3" in out
    assert "Sin cubrir" not in out
    assert {gate.name: gate for gate in calls}["pytest"].env == {"CADENZA_REQUIRE_POSTGRES": "1"}


def test_the_web_gates_need_the_installed_dependencies(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls: list[str] = []

    def runner(gate: Gate) -> tuple[int, str]:
        calls.append(gate.name)
        return 0, ""

    code = _main([], runner=runner, web_dir=tmp_path)  # sin node_modules

    out = capsys.readouterr().out
    assert code == 1
    assert not any(name.startswith("npm") for name in calls)
    assert "npm ci" in out
    assert "Puertas locales en rojo" in out


def test_a_tree_that_changes_during_the_run_turns_it_red(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _main(["--sin-web"], git=_git(commits=("354b8b3", "abcdef0")))

    out = capsys.readouterr().out
    assert code == 1
    assert "El árbol cambió durante la pasada" in out
    assert "Puertas locales en rojo sobre 354b8b3" in out


def test_an_old_node_is_noted(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()

    _main([], node_major=lambda: 20, web_dir=tmp_path)

    assert "Node 20: la CI usa Node 24" in capsys.readouterr().out
