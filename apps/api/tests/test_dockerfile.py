"""Orden de las capas del Dockerfile de la API (#205).

Las dependencias y los pesos de HOMR se instalan antes de copiar el código, y la etapa final
copia el entorno virtual aparte del código: así un cambio de código no los reinstala ni vuelve a
copiar el entorno virtual, y la caché de construcción del servidor no crece unos 2,5 GB en cada
despliegue.
"""

import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _stage(name: str) -> list[str]:
    """Instrucciones de una etapa del Dockerfile, sin comentarios y con las líneas unidas."""
    instructions: list[str] = []
    pending = ""
    stage: str | None = None
    for raw in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending += line.removesuffix("\\").strip() + " "
        if line.endswith("\\"):
            continue
        instruction, pending = " ".join(pending.split()), ""
        if instruction.upper().startswith("FROM "):
            stage = instruction.split()[-1]
        elif stage == name:
            instructions.append(instruction)
    return instructions


def _only(instructions: list[str], matches: Callable[[str], bool]) -> int:
    found = [n for n, instruction in enumerate(instructions) if matches(instruction)]
    assert len(found) == 1, found
    return found[0]


def _installs_dependencies(instruction: str) -> bool:
    return instruction.startswith("RUN uv sync") and "--no-install-workspace" in instruction


def _is_code(instruction: str) -> bool:
    return instruction in ("COPY apps/api/ apps/api/", "COPY packages/ packages/")


def test_dependencies_and_weights_are_installed_without_the_code() -> None:
    deps = _stage("deps")

    dependencies = _only(deps, _installs_dependencies)
    weights = _only(deps, lambda instruction: "homr --init" in instruction)

    assert dependencies < weights
    assert not any(_is_code(instruction) for instruction in deps)


def test_the_code_and_the_workspace_packages_come_after_the_dependencies() -> None:
    builder = _stage("builder")

    code = [n for n, instruction in enumerate(builder) if _is_code(instruction)]
    workspace = _only(builder, lambda instruction: instruction.startswith("RUN uv sync"))

    assert len(code) == 2 and max(code) < workspace
    assert not _installs_dependencies(builder[workspace])


def test_every_workspace_member_is_declared_before_installing_dependencies() -> None:
    # `uv sync --frozen` necesita el pyproject.toml de todos los miembros del workspace.
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    members = pyproject["tool"]["uv"]["workspace"]["members"]
    deps = _stage("deps")
    dependencies = _only(deps, _installs_dependencies)

    copied = {
        source
        for instruction in deps[:dependencies]
        if instruction.startswith("COPY ")
        for source in instruction.split()[1:-1]
        if source.endswith("pyproject.toml")
    }

    assert copied == {"pyproject.toml", *(f"{member}/pyproject.toml" for member in members)}


def test_the_final_stage_copies_the_environment_apart_from_the_code() -> None:
    runner = _stage("runner")
    copies = [instruction for instruction in runner if instruction.startswith("COPY --from=")]

    # El entorno virtual de las dependencias sale de deps, que no cambia con el código: sus capas
    # se reutilizan. Los paquetes del workspace y el código, que sí cambian, van aparte.
    assert copies == [
        "COPY --from=deps /app/.venv /app/.venv",
        "COPY --from=builder /workspace-site/ /app/.venv/lib/python3.12/site-packages/",
        "COPY --from=builder /app/apps /app/apps",
        "COPY --from=builder /app/packages /app/packages",
    ]
