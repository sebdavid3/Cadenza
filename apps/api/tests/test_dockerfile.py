"""Orden de las capas del Dockerfile de la API (#205).

Las dependencias y los pesos de HOMR se instalan antes de copiar el código, y la etapa final
copia el entorno virtual aparte del código: así un cambio de código no los reinstala ni vuelve a
copiar el entorno virtual, y la caché de construcción del servidor no crece unos 2,5 GB en cada
despliegue.

La imagen se construye para la CPU por defecto (la CI y el compose de desarrollo) o para una GPU
NVIDIA, con ONNX Runtime con CUDA y los pesos de las dos; el compose de producción la construye con
GPU, reserva una y deja volver a la CPU desde el .env (#268, ADR-0066).
"""

import re
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


def _members() -> list[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    members: list[str] = pyproject["tool"]["uv"]["workspace"]["members"]
    return members


def _copied_sources(instructions: list[str]) -> list[str]:
    """Fuentes de las instrucciones COPY que toman archivos del contexto, no de otra etapa."""
    return [
        source
        for instruction in instructions
        if instruction.startswith("COPY ") and "--from=" not in instruction
        for source in instruction.split()[1:-1]
        if not source.startswith("--")
    ]


def test_dependencies_and_weights_are_installed_from_the_manifests_alone() -> None:
    # En deps solo entran el lockfile y los pyproject.toml, de todos los miembros del workspace,
    # que `uv sync --frozen` necesita: ni una línea de código, o cada cambio de código
    # reinstalaría las dependencias.
    deps = _stage("deps")

    dependencies = _only(deps, _installs_dependencies)
    weights = _only(deps, lambda instruction: "homr --init" in instruction)

    assert dependencies < weights
    assert sorted(_copied_sources(deps)) == sorted(
        ["pyproject.toml", "uv.lock", *(f"{member}/pyproject.toml" for member in _members())]
    )
    assert not _copied_sources(deps[dependencies:])


def test_the_code_and_the_workspace_packages_come_after_the_dependencies() -> None:
    builder = _stage("builder")
    deps = _stage("deps")

    code = [n for n, instruction in enumerate(builder) if instruction.startswith("COPY ")]
    workspace = _only(builder, lambda instruction: instruction.startswith("RUN uv sync"))

    assert _copied_sources(builder) == ["apps/api/", "packages/"]
    assert max(code) < workspace
    # Las mismas opciones que en deps: con otras, la etapa final no tendría lo que se instalara
    # de más, porque de esta instalación solo copia los paquetes del workspace.
    assert (
        builder[workspace] + " --no-install-workspace" == deps[_only(deps, _installs_dependencies)]
    )


def test_the_final_stage_copies_the_environment_apart_from_the_code() -> None:
    runner = _stage("runner")
    copies = [instruction for instruction in runner if instruction.startswith("COPY --from=")]

    # El entorno virtual de las dependencias sale de deps (venv es deps con CPU o con GPU,
    # ADR-0066), que no cambia con el código: sus capas se reutilizan. Los paquetes del workspace y
    # el código, que sí cambian, van aparte.
    assert copies == [
        "COPY --from=venv /app/.venv /app/.venv",
        "COPY --from=builder /workspace-site/ /app/.venv/lib/python3.12/site-packages/",
        "COPY --from=builder /app/apps /app/apps",
        "COPY --from=builder /app/packages /app/packages",
    ]


def test_the_build_fails_if_a_workspace_file_is_left_behind() -> None:
    # De la instalación del workspace solo se copian los dist-info y los .pth: la construcción
    # comprueba que estén todos los archivos que esos paquetes declaran.
    runner = _stage("runner")

    check = _only(runner, lambda instruction: "locate_file" in instruction)

    assert check > max(n for n, i in enumerate(runner) if i.startswith("COPY --from="))
    assert "startswith('cadenza-')" in runner[check]
    # Distribution.files omite lo que no existe desde Python 3.12: la lista sale del RECORD.
    assert "read_text('RECORD')" in runner[check]


def _dockerfile() -> list[str]:
    return [
        line.strip()
        for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _api_service() -> str:
    """El bloque del servicio api de docker-compose.prod.yml, sin comentarios."""
    text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    block = text.split("\n  api:\n", 1)[1].split("\n  web:\n", 1)[0]
    return "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))


def test_the_image_is_built_for_the_cpu_unless_asked() -> None:
    lines = _dockerfile()

    # El ARG global va antes del primer FROM, para que FROM lo pueda usar.
    assert lines[0] == "ARG CADENZA_OMR_DEVICE=cpu"
    assert "FROM deps AS deps-cpu" in lines
    assert "FROM deps AS deps-gpu" in lines
    assert "FROM deps-${CADENZA_OMR_DEVICE} AS venv" in lines


def test_the_gpu_environment_brings_cuda_and_the_weights_of_both_devices() -> None:
    deps = _stage("deps")
    gpu = _stage("deps-gpu")

    # Los pesos fp32 de la CPU, en deps; los fp16 de CUDA, además, en deps-gpu.
    assert any("homr --init" in instruction for instruction in deps)
    (install,) = gpu
    assert "uv pip uninstall --python /app/.venv/bin/python onnxruntime" in install
    gpu_runtime = '"onnxruntime-gpu[cuda,cudnn]==1.26.0"'
    # Sin la caché de uv, que repetiría los wheels de NVIDIA en la capa.
    assert f"uv pip install --no-cache --python /app/.venv/bin/python {gpu_runtime}" in install
    assert (
        "download_weights(segnet_use_gpu=True, transformer_use_gpu=True, coreml_encoder=False)"
        in install
    )
    assert _stage("deps-cpu") == []


def test_the_build_checks_that_onnxruntime_matches_the_device() -> None:
    runner = _stage("runner")

    check = _only(runner, lambda instruction: "CUDAExecutionProvider" in instruction)
    assert runner[check - 1] == "ARG CADENZA_OMR_DEVICE"
    assert "(sys.argv[1] == 'gpu')" in runner[check]
    assert runner[check].endswith('"$CADENZA_OMR_DEVICE"')


def test_prod_builds_for_the_gpu_and_reserves_one() -> None:
    api = _api_service()

    assert re.search(r"\n {6}args:\n {8}CADENZA_OMR_DEVICE: gpu\n", api)
    assert "CADENZA_OMR_USE_GPU: ${CADENZA_OMR_USE_GPU:-true}" in api
    # Con CADENZA_API_GPUS=0 el contenedor arranca sin GPU (también si falla el controlador).
    assert re.search(
        r"\n {4}deploy:\n {6}resources:\n {8}reservations:\n {10}devices:\n"
        r" {12}- driver: nvidia\n {14}count: \$\{CADENZA_API_GPUS:-1\}\n"
        r" {14}capabilities: \[gpu\]\n",
        api,
    )


def test_the_development_compose_stays_on_the_cpu() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "CADENZA_OMR_DEVICE" not in compose
    assert "driver: nvidia" not in compose.split("\n  ml-batch:", 1)[0]
