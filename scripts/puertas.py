"""Las puertas de calidad en local: lo mismo que la CI, mientras la de GitHub está bloqueada (#349).

Desde el 2026-11-08, GitHub Actions no arranca por un cobro pendiente de la cuenta. Por decisión
del responsable, se fusiona con estas puertas en verde, la revisión independiente hecha y una
nota en el PR, que este script deja lista para pegar. Desde la raíz del repositorio:

    uv run --no-sync python scripts/puertas.py             # Python y web, como la CI
    uv run --no-sync python scripts/puertas.py --sin-web   # solo Python
    uv run --no-sync python scripts/puertas.py --docker    # y además el job de Docker de la CI

Nunca `uv sync` a secas: desinstalaría HOMR (`CLAUDE.md` §7). Hay que lanzarlo con `uv run`,
para que la comprobación de HOMR mire el entorno del proyecto. Pasa todas las puertas aunque
falle una, para verlas todas de una vez, y la línea para el PR dice lo que no se cubrió.

Diferencias con la CI, a propósito:
- Vitest corre con dos procesos (`--maxWorkers=2`). Por defecto usa tantos como hilos menos uno:
  15 en un portátil de 16 hilos, frente a 3 en la CI. Así, los tiempos de 5 s de algunas pruebas
  se agotaban (2026-11-08: fallaban 15 que pasan solas). El verde local no garantiza que esos
  tiempos aguanten en las vCPU de la CI.
- Las pruebas de PostgreSQL solo corren con `CADENZA_TEST_POSTGRES_URL`, y entonces se exigen como
  en la CI (`CADENZA_REQUIRE_POSTGRES=1`), con `pg_dump` y `pg_restore` de PostgreSQL 16.
- `--docker` construye desde la carpeta de trabajo (con sus fines de línea y sus archivos
  ignorados), no desde un checkout limpio como la CI.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web"
CI_NODE_MAJOR = 24
CI_POSTGRES_MAJOR = 16
_UV = ("uv", "run", "--no-sync")
_PYTEST_PART = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed)\b")
# La salida de los hijos en UTF-8 (como el Linux de la CI) y sin búfer, para verla en directo
# a través de la tubería.
_CHILD_ENV = {"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
_INCIPIT_IN_IMAGE = (
    'test "$(id -u)" = 10001 && touch /app/data/artifacts/.prueba && '
    "python apps/api/tests/fixtures/transcribe_incipit.py"
)


@dataclass(frozen=True)
class Gate:
    """Una puerta: su nombre, la orden, la carpeta, las variables que añade al entorno y la
    puerta de la que depende (la imagen que usa): si esa falla, esta no se ejecuta."""

    name: str
    command: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)
    requires: str | None = None


@dataclass(frozen=True)
class Result:
    name: str
    ok: bool
    seconds: float
    output: str


Runner = Callable[[Gate], tuple[int, str]]
Git = Callable[..., str]


def _docker_gates() -> list[Gate]:
    """El job `docker` de la CI, paso a paso y con las mismas órdenes."""

    compose_env = {
        # Generados al vuelo, como en la CI: el compose los exige, pero no se usan.
        "CADENZA_POSTGRES_PASSWORD": secrets.token_hex(16),
        "CADENZA_AUTH_SECRET_KEY": secrets.token_hex(32),
        "CADENZA_PUBLIC_ORIGIN": "https://cadenza.example",
    }
    compose = ("docker", "compose", "-f", "docker-compose.prod.yml")
    return [
        Gate("docker api", ("docker", "build", "-t", "cadenza-api:local", "."), REPO),
        Gate(
            "docker api: íncipit sin root",
            (
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--tmpfs",
                "/home/cadenza:uid=10001,gid=10001,mode=0755",
                "--mount",
                "type=volume,dst=/app/data/artifacts",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "cadenza-api:local",
                "sh",
                "-c",
                _INCIPIT_IN_IMAGE,
            ),
            REPO,
            requires="docker api",
        ),
        Gate(
            "docker web",
            (
                "docker",
                "build",
                "-f",
                "Dockerfile.web",
                "--build-arg",
                "VITE_REGISTRATION_ENABLED=true",
                "-t",
                "cadenza-web:local",
                ".",
            ),
            REPO,
        ),
        Gate(
            "docker copias",
            ("docker", "build", "-f", "Dockerfile.backup", "-t", "cadenza-backup:local", "."),
            REPO,
        ),
        Gate(
            "docker copias: pg_dump",
            (
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "pg_dump",
                "cadenza-backup:local",
                "--version",
            ),
            REPO,
            requires="docker copias",
        ),
        Gate(
            "docker copias: ayuda",
            ("docker", "run", "--rm", "cadenza-backup:local", "--help"),
            REPO,
            requires="docker copias",
        ),
        Gate("compose", (*compose, "config", "--quiet"), REPO, compose_env),
        Gate(
            "compose con copias",
            (*compose, "--profile", "backup", "config", "--quiet"),
            REPO,
            compose_env,
        ),
    ]


def build_plan(
    *, web: bool, docker: bool, postgres: bool = False, web_dir: Path = WEB
) -> list[Gate]:
    """Las puertas en el orden de la CI (`.github/workflows/ci.yml`)."""

    pytest_env = {"CADENZA_REQUIRE_POSTGRES": "1"} if postgres else {}
    plan = [
        Gate("ruff", (*_UV, "ruff", "check", "."), REPO),
        Gate("black", (*_UV, "black", "--check", "."), REPO),
        Gate("mypy", (*_UV, "mypy", "packages", "apps"), REPO),
        # -rs: por qué se omitió cada prueba omitida.
        Gate("pytest", (*_UV, "pytest", "-rs"), REPO, pytest_env),
    ]
    if web:
        plan += [
            Gate("npm lint", ("npm", "run", "lint"), web_dir),
            Gate("npm format:check", ("npm", "run", "format:check"), web_dir),
            Gate("npm test", ("npm", "run", "test", "--", "--maxWorkers=2"), web_dir),
            Gate("npm build", ("npm", "run", "build"), web_dir),
        ]
    if docker:
        plan += _docker_gates()
    return plan


def run_live(gate: Gate) -> tuple[int, str]:
    """Ejecuta la puerta mostrando su salida mientras corre, y la devuelve."""

    executable = shutil.which(gate.command[0])
    if executable is None:
        message = f"no se encuentra `{gate.command[0]}` en el PATH"
        print(message)
        return 127, message
    lines: list[str] = []
    try:
        process = subprocess.Popen(
            [executable, *gate.command[1:]],
            cwd=gate.cwd,
            env={**os.environ, **_CHILD_ENV, **gate.env},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        # Un fallo al lanzarla es un fallo de esa puerta, no de la pasada.
        message = f"no se pudo ejecutar `{gate.command[0]}`: {exc}"
        print(message)
        return 126, message
    with process:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            lines.append(line)
    return process.returncode, "".join(lines)


def run_gates(plan: Sequence[Gate], runner: Runner) -> list[Result]:
    """Todas las puertas, aunque falle alguna; las que usan una imagen que no se construyó no se
    ejecutan (probarían una imagen vieja, o se la bajarían)."""

    results = []
    failed: set[str] = set()
    for gate in plan:
        if gate.requires is not None and gate.requires in failed:
            message = f"no se ejecutó: falló {gate.requires}"
            print(f"\n=== {gate.name}: {message}", flush=True)
            results.append(Result(gate.name, ok=False, seconds=0.0, output=message))
            failed.add(gate.name)
            continue
        print(f"\n=== {gate.name}: {' '.join(gate.command)}", flush=True)
        start = time.monotonic()
        code, output = runner(gate)
        results.append(Result(gate.name, code == 0, time.monotonic() - start, output))
        if code != 0:
            failed.add(gate.name)
    return results


def pytest_counts(output: str) -> str | None:
    """«2169 passed, 5 skipped» de la última línea de resumen de pytest (sin los avisos)."""

    for line in reversed(output.splitlines()):
        parts = _PYTEST_PART.findall(line)
        if parts:
            return ", ".join(f"{count} {kind}" for count, kind in parts)
    return None


def pr_line(
    results: Sequence[Result],
    *,
    commit: str,
    dirty: bool,
    uncovered: Sequence[str] = (),
) -> str:
    """La línea para el PR: el commit, cada puerta (las que fallan, marcadas) y lo que no se
    cubrió, para que una pasada parcial no parezca la de la CI."""

    names = []
    for result in results:
        counts = pytest_counts(result.output) if result.name == "pytest" else None
        name = f"{result.name} ({counts})" if counts else result.name
        names.append(name if result.ok else f"{name} (FALLA)")
    if not all(result.ok for result in results):
        state = "en rojo"
    elif uncovered:
        state = "en verde, parciales"
    else:
        state = "en verde"
    where = f"{commit}, con cambios sin comitear" if dirty else commit
    line = f"Puertas locales {state} sobre {where} (`scripts/puertas.py`): {', '.join(names)}."
    if uncovered:
        line += f" Sin cubrir: {'; '.join(uncovered)}."
    return line


def _git(*args: str) -> str:
    """La salida de git en UTF-8, y lo que no lo sea, con `surrogateescape`, la convención con la
    que `_snapshot` vuelve a codificar la huella: con la codificación del sistema (cp1252 en
    Windows), un cambio sin comitear con «Í» dejaba `stdout` en `None` (#371)."""
    done = subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        check=False,
    )
    return done.stdout.strip()


@dataclass(frozen=True)
class _Tree:
    commit: str
    status: str
    content: str

    @property
    def dirty(self) -> bool:
        return bool(self.status)


def _snapshot(git: Git) -> _Tree:
    """El commit, el estado y una huella de los cambios sin comitear: si un archivo que ya
    estaba modificado cambia durante la pasada, el estado es el mismo, pero la huella no."""

    changes = (
        git("diff", "HEAD", "--binary") + "\0" + git("ls-files", "--others", "--exclude-standard")
    )
    return _Tree(
        commit=git("rev-parse", "--short", "HEAD"),
        status=git("status", "--porcelain"),
        content=hashlib.sha256(changes.encode("utf-8", "surrogateescape")).hexdigest(),
    )


def _homr_installed() -> bool:
    return importlib.util.find_spec("homr") is not None


def _node_major() -> int | None:
    node = shutil.which("node")
    if node is None:
        return None
    done = subprocess.run(
        [node, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    match = re.match(r"v(\d+)", done.stdout.strip())
    return int(match.group(1)) if match else None


def _pg_dump_major() -> int | None:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        return None
    done = subprocess.run(
        [pg_dump, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    match = re.search(r"(\d+)(?:\.\d+)*\s*$", done.stdout.strip())
    return int(match.group(1)) if match else None


def _web_deps_outdated(web_dir: Path) -> bool:
    """Si lo instalado no es lo que fija `package-lock.json`: tras fusionar un cambio de
    dependencias, `npm ci` (la CI lo hace siempre).

    Compara las versiones de cada paquete con las del lockfile oculto que npm deja en
    `node_modules` (por fechas no vale: cambiar de rama reescribe `package-lock.json`). Un
    paquete opcional que falta es el de otra plataforma, no un desfase.
    """

    lock_path = web_dir / "package-lock.json"
    installed_path = web_dir / "node_modules" / ".package-lock.json"
    if not lock_path.is_file() or not installed_path.is_file():
        return False
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8")).get("packages", {})
        installed = json.loads(installed_path.read_text(encoding="utf-8")).get("packages", {})
    except (OSError, ValueError):
        return True
    for key, entry in lock.items():
        if not key:
            continue
        have = installed.get(key)
        if have is None:
            if not entry.get("optional"):
                return True
        elif have.get("version") != entry.get("version"):
            return True
    return any(key not in lock for key in installed)


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner = run_live,
    homr_installed: Callable[[], bool] = _homr_installed,
    node_major: Callable[[], int | None] = _node_major,
    pg_dump_major: Callable[[], int | None] = _pg_dump_major,
    git: Git = _git,
    web_dir: Path = WEB,
) -> int:
    parser = argparse.ArgumentParser(
        description="Las puertas de calidad de la CI, en local (#349)."
    )
    parser.add_argument("--sin-web", action="store_true", help="Solo las puertas de Python")
    parser.add_argument("--docker", action="store_true", help="También el job de Docker de la CI")
    args = parser.parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        # Vite y pytest escriben caracteres que la consola de Windows no siempre sabe mostrar.
        reconfigure(errors="replace")

    web = not args.sin_web
    postgres = bool(os.environ.get("CADENZA_TEST_POSTGRES_URL"))
    notes: list[str] = []
    uncovered: list[str] = []
    if not web:
        uncovered.append("web (--sin-web)")
    if not args.docker:
        uncovered.append("imágenes de Docker (sin --docker)")
    if postgres:
        if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
            notes.append(
                "Con CADENZA_TEST_POSTGRES_URL se exigen pg_dump y pg_restore (la CI usa los de "
                "PostgreSQL 16), y no están en el PATH: la prueba de las copias fallará."
            )
        elif (major := pg_dump_major()) != CI_POSTGRES_MAJOR:
            notes.append(
                f"pg_dump {major or '(versión desconocida)'}: la CI usa el de PostgreSQL "
                f"{CI_POSTGRES_MAJOR}, y con otra versión la prueba de las copias puede no ser la "
                "misma."
            )
    else:
        uncovered.append("PostgreSQL (sin CADENZA_TEST_POSTGRES_URL)")
        notes.append(
            "Las pruebas de PostgreSQL se omiten: la CI las pasa contra un PostgreSQL 16; aquí "
            "hace falta CADENZA_TEST_POSTGRES_URL (y entonces se exigen, como en la CI)."
        )
    if not homr_installed():
        notes.append(
            "HOMR no está instalado: se omiten las pruebas del motor real (ver el README; "
            "nunca `uv sync` a secas). La CI tampoco lo instala."
        )
    if web:
        major = node_major()
        if major != CI_NODE_MAJOR:
            notes.append(f"Node {major or '(no encontrado)'}: la CI usa Node {CI_NODE_MAJOR}.")
        if _web_deps_outdated(web_dir):
            notes.append(
                "Lo instalado en apps/web no es lo que fija package-lock.json: ejecuta `npm ci` "
                "(la CI lo hace siempre)."
            )

    plan = build_plan(web=web, docker=args.docker, postgres=postgres, web_dir=web_dir)
    skipped: list[Result] = []
    if web and not (web_dir / "node_modules").is_dir():
        message = f"faltan las dependencias de la web: ejecuta `npm ci` en {web_dir}"
        skipped = [
            Result(gate.name, ok=False, seconds=0.0, output=message)
            for gate in plan
            if gate.name.startswith("npm ")
        ]
        plan = [gate for gate in plan if not gate.name.startswith("npm ")]

    before = _snapshot(git)
    results = run_gates(plan, runner) + skipped
    after = _snapshot(git)
    if after != before:
        # Otro commit, otra rama u otra sesión en la misma carpeta: lo probado no es lo que hay.
        notes.insert(0, "El árbol cambió durante la pasada: lo probado no es lo que hay ahora.")
        results.append(Result("árbol sin cambios", ok=False, seconds=0.0, output=""))

    print("\n=== Resumen")
    for result in results:
        mark = "OK    " if result.ok else "FALLA "
        print(f"{mark} {result.name} ({result.seconds:.0f} s)")
        if not result.ok and result.output and result in skipped:
            print(f"       {result.output}")
    if notes:
        print("\nA tener en cuenta:")
        for note in notes:
            print(f"- {note}")

    print("\nPara el PR:")
    print(pr_line(results, commit=before.commit, dirty=before.dirty, uncovered=uncovered))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
