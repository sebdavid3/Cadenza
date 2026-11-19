"""La imagen y el servicio `stats` de las cifras públicas de los errores de HOMR (#423, ADR-0073).

Un servicio aparte de la API, sin HOMR ni GPU, que lee la base y no escribe ningún archivo: corre
sin root, con el sistema de archivos de solo lectura y el corpus montado de solo lectura.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _instructions() -> list[str]:
    """Las instrucciones de `Dockerfile.stats`, sin comentarios y con las líneas unidas."""
    instructions: list[str] = []
    pending = ""
    for raw in (ROOT / "Dockerfile.stats").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending += line.removesuffix("\\").strip() + " "
        if not line.endswith("\\"):
            instructions.append(" ".join(pending.split()))
            pending = ""
    return instructions


def _stats_service() -> str:
    text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    block = text.split("\n  stats:\n", 1)[1].split("\n  backup:\n", 1)[0]
    return "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))


def test_the_image_installs_only_learning_and_persistence_before_the_code() -> None:
    lines = _instructions()
    sync = [i for i, line in enumerate(lines) if line.startswith("RUN uv sync")]
    code = lines.index("COPY packages/ packages/")

    assert len(sync) == 2
    assert sync[0] < code < sync[1]
    for index in sync:
        assert "--package cadenza-learning --package cadenza-persistence" in lines[index]
        assert "--frozen --no-dev" in lines[index]
        assert "homr" not in lines[index]
    assert "--no-install-workspace" in lines[sync[0]]
    assert "COPY ml/tables_report.py ml/public_stats.py ml/" in lines


def test_the_image_checks_the_import_and_runs_without_root() -> None:
    lines = _instructions()

    assert any(line.startswith('RUN python -c "import ml.public_stats"') for line in lines)
    assert "--uid 10001" in next(line for line in lines if "useradd" in line)
    assert lines[-3] == "USER cadenza"
    assert lines[-2] == 'ENTRYPOINT ["python", "-m", "ml.public_stats"]'


def test_the_service_recomputes_every_five_minutes_with_least_privilege() -> None:
    service = _stats_service()

    assert "dockerfile: Dockerfile.stats" in service
    assert (
        'command: ["--every", "${CADENZA_STATS_EVERY_SECONDS:-300}", "--corpus-dir",'
        ' "/app/corpus"]'
    ) in service
    assert "- ${CADENZA_STATS_CORPUS_DIR:-./data/stats-corpus}:/app/corpus:ro" in service
    assert "read_only: true" in service
    assert "cap_drop:\n      - ALL" in service
    assert "no-new-privileges:true" in service
    assert "ports:" not in service
    assert "driver: nvidia" not in service
    assert "artifacts_data" not in service  # no ve las fotos
