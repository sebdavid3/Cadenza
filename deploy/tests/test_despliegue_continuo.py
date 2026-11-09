"""Pruebas de `deploy/despliegue-continuo.sh` (#337, ADR-0062).

Cada prueba monta un remoto `origin` y un clon de «producción» con git de verdad, y pone delante
del PATH versiones falsas de `docker`, `gh` y `curl`:

- `docker` apunta cada llamada en un registro y falla en la orden que contenga el trozo que pida
  la prueba (`backup --output`, `verify --archive`, `up -d --build` o `build backup`);
- `gh` aplica el filtro `--jq` del script con `jq` sobre ejecuciones de la CI con la forma de la
  API de GitHub (`/actions/runs`), así que el filtro también se prueba;
- `curl` apunta la URL y responde sano salvo cuando el commit desplegado es el que la prueba marca
  como roto.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "despliegue-continuo.sh"

FAKE_DOCKER = """#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
# FAKE_DOCKER_FALLA: el trozo de la orden que debe fallar («backup --output», «build backup»...).
if [ -n "${FAKE_DOCKER_FALLA:-}" ]; then
    case " $* " in
        *"$FAKE_DOCKER_FALLA"*) exit 1 ;;
    esac
fi
exit 0
"""

FAKE_GH = """#!/bin/sh
echo "gh $*" >> "$FAKE_LOG"
[ -z "${FAKE_GH_FALLA:-}" ] || exit 1
filtro=""
while [ $# -gt 0 ]; do
    if [ "$1" = "--jq" ]; then filtro="$2"; shift; fi
    shift
done
jq -r "$filtro" "$FAKE_RUNS"
"""

FAKE_CURL = """#!/bin/sh
for ultimo in "$@"; do :; done
echo "curl $ultimo" >> "$FAKE_LOG"
if [ -n "${FAKE_MALO:-}" ] && [ "$(git rev-parse HEAD)" = "$FAKE_MALO" ]; then
    exit 22
fi
echo '{"status":"healthy","database":"connected"}'
"""

FAKE_LIMPIEZA = """#!/bin/sh
echo "limpieza" >> "$FAKE_LOG"
"""

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Prueba",
    "GIT_AUTHOR_EMAIL": "prueba@example.com",
    "GIT_COMMITTER_NAME": "Prueba",
    "GIT_COMMITTER_EMAIL": "prueba@example.com",
}


def _git(cwd: Path, *args: str) -> str:
    resultado = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
    )
    return resultado.stdout.strip()


def _ejecutable(ruta: Path, contenido: str) -> None:
    ruta.write_text(contenido, encoding="utf-8")
    ruta.chmod(0o755)


def run(
    status: str = "completed",
    conclusion: str | None = "success",
    *,
    attempt: int = 1,
    name: str = "CI",
    branch: str = "main",
    created: str = "2026-11-16T10:00:00Z",
) -> dict[str, Any]:
    """Una ejecución de flujo con los campos que lee el script."""
    return {
        "name": name,
        "event": "push",
        "head_branch": branch,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "run_attempt": attempt,
        "created_at": created,
    }


VERDE = [run()]


@dataclass
class Entorno:
    tmp: Path
    desarrollo: Path
    produccion: Path
    estado: Path
    registro: Path
    bin: Path

    def publicar(self, texto: str, archivo: str = "app.txt") -> str:
        """Un commit nuevo en origin/main, como un merge de la promoción."""
        (self.desarrollo / archivo).write_text(texto, encoding="utf-8")
        _git(self.desarrollo, "add", archivo)
        _git(self.desarrollo, "commit", "-qm", texto)
        _git(self.desarrollo, "push", "-q", "origin", "main")
        return _git(self.desarrollo, "rev-parse", "HEAD")

    def ejecutar(
        self,
        *args: str,
        runs: list[dict[str, Any]] | None = None,
        gh_falla: bool = False,
        malo: str = "",
        docker_falla: str = "",
        extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        runs_json = self.tmp / "runs.json"
        runs_json.write_text(
            json.dumps({"workflow_runs": VERDE if runs is None else runs}), encoding="utf-8"
        )
        env = {
            **{k: v for k, v in os.environ.items() if k != "CADENZA_WEB_PORT"},
            **GIT_ENV,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.tmp / "home"),
            "CADENZA_DESPLIEGUE_ESTADO": str(self.estado),
            "CADENZA_DESPLIEGUE_ESPERA": "1",
            "CADENZA_DESPLIEGUE_INTERVALO": "0.2",
            "FAKE_LOG": str(self.registro),
            "FAKE_RUNS": str(runs_json),
            "FAKE_GH_FALLA": "1" if gh_falla else "",
            "FAKE_MALO": malo,
            "FAKE_DOCKER_FALLA": docker_falla,
            **(extra or {}),
        }
        return subprocess.run(
            ["sh", str(self.produccion / "deploy" / "despliegue-continuo.sh"), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def head(self) -> str:
        return _git(self.produccion, "rev-parse", "HEAD")

    def llamadas(self) -> list[str]:
        if not self.registro.exists():
            return []
        return self.registro.read_text(encoding="utf-8").splitlines()

    def docker(self) -> list[str]:
        return [linea for linea in self.llamadas() if linea.startswith("docker ")]

    def ups(self) -> int:
        return sum(" up -d --build" in c for c in self.docker())


@pytest.fixture()
def entorno(tmp_path: Path) -> Entorno:
    for herramienta in ("flock", "jq"):
        if shutil.which(herramienta) is None:
            pytest.skip(f"las pruebas necesitan {herramienta}")
    origen = tmp_path / "origen.git"
    desarrollo = tmp_path / "desarrollo"
    produccion = tmp_path / "produccion"
    binarios = tmp_path / "bin"
    binarios.mkdir()
    (tmp_path / "home").mkdir()
    _ejecutable(binarios / "docker", FAKE_DOCKER)
    _ejecutable(binarios / "gh", FAKE_GH)
    _ejecutable(binarios / "curl", FAKE_CURL)

    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origen))
    _git(tmp_path, "clone", "-q", str(origen), str(desarrollo))
    _git(desarrollo, "switch", "-q", "-c", "main")
    (desarrollo / "deploy").mkdir()
    shutil.copy(SCRIPT, desarrollo / "deploy" / "despliegue-continuo.sh")
    _ejecutable(desarrollo / "deploy" / "limpieza-docker.sh", FAKE_LIMPIEZA)
    (desarrollo / "app.txt").write_text("v1", encoding="utf-8")
    _git(desarrollo, "add", "deploy", "app.txt")
    _git(desarrollo, "commit", "-qm", "v1")
    _git(desarrollo, "push", "-q", "origin", "main")
    _git(tmp_path, "clone", "-q", str(origen), str(produccion))

    return Entorno(
        tmp=tmp_path,
        desarrollo=desarrollo,
        produccion=produccion,
        estado=tmp_path / "estado",
        registro=tmp_path / "llamadas.log",
        bin=binarios,
    )


# --- Sin novedad --------------------------------------------------------------------------------


def test_sin_commits_nuevos_no_hace_nada_ni_escribe(entorno: Entorno) -> None:
    antes = entorno.head()

    resultado = entorno.ejecutar()

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout == ""
    assert entorno.head() == antes
    assert entorno.llamadas() == []


def test_en_pausa_no_hace_nada(entorno: Entorno) -> None:
    antes = entorno.head()
    entorno.publicar("v2")
    entorno.estado.mkdir()
    (entorno.estado / "pausado").touch()

    resultado = entorno.ejecutar()

    assert resultado.returncode == 0
    assert resultado.stdout == ""
    assert entorno.head() == antes
    assert entorno.llamadas() == []


def test_simular_dice_lo_que_haria_sin_cambiar_nada(entorno: Entorno) -> None:
    antes = entorno.head()
    nuevo = entorno.publicar("v2")

    resultado = entorno.ejecutar("--simular")

    assert resultado.returncode == 0
    assert f"desplegaría {antes[:7]} -> {nuevo[:7]}" in resultado.stdout
    assert entorno.head() == antes
    assert entorno.docker() == []


# --- Despliegue ---------------------------------------------------------------------------------


def test_commit_nuevo_con_ci_verde_copia_avanza_reconstruye_y_limpia(entorno: Entorno) -> None:
    nuevo = entorno.publicar("v2")

    resultado = entorno.ejecutar()

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert entorno.head() == nuevo
    assert _git(entorno.produccion, "branch", "--show-current") == "main"
    docker = entorno.docker()
    copia = next(i for i, c in enumerate(docker) if " backup --output /backups/" in c)
    verifica = next(i for i, c in enumerate(docker) if " verify --archive /backups/" in c)
    sube = next(i for i, c in enumerate(docker) if " up -d --build" in c)
    imagen = next(i for i, c in enumerate(docker) if " build backup" in c)
    assert copia < verifica < sube < imagen
    assert f"antes-{nuevo[:7]}" in docker[copia]
    assert entorno.llamadas()[-1] == "limpieza"
    assert f"desplegado {nuevo[:7]}" in resultado.stdout


def test_primer_paso_desde_dev_cambia_a_main(entorno: Entorno) -> None:
    _git(entorno.produccion, "switch", "-q", "-c", "dev")
    nuevo = entorno.publicar("v2")

    resultado = entorno.ejecutar()

    assert resultado.returncode == 0, resultado.stdout
    assert _git(entorno.produccion, "branch", "--show-current") == "main"
    assert entorno.head() == nuevo


def test_lee_el_puerto_de_la_web_del_env(entorno: Entorno) -> None:
    (entorno.produccion / ".env").write_text("CADENZA_WEB_PORT=9090\n", encoding="utf-8")
    entorno.publicar("v2")

    resultado = entorno.ejecutar()

    assert resultado.returncode == 0, resultado.stdout
    assert "curl http://127.0.0.1:9090/api/health" in entorno.llamadas()


def test_un_archivo_suelto_que_el_commit_no_trae_no_estorba(entorno: Entorno) -> None:
    (entorno.produccion / ".env.bak-20261104").write_text("copia", encoding="utf-8")
    nuevo = entorno.publicar("v2")

    resultado = entorno.ejecutar()

    assert resultado.returncode == 0, resultado.stdout
    assert entorno.head() == nuevo


def test_si_falla_la_imagen_de_copias_el_despliegue_sigue(entorno: Entorno) -> None:
    nuevo = entorno.publicar("v2")

    resultado = entorno.ejecutar(docker_falla="build backup")

    assert resultado.returncode == 0, resultado.stdout
    assert entorno.head() == nuevo
    assert entorno.ups() == 1
    assert "no se reconstruyó la imagen de copias" in resultado.stdout


# --- La CI --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "runs",
    [
        pytest.param([], id="sin-ejecucion"),
        pytest.param([run("in_progress")], id="en-curso"),
        pytest.param([run("queued")], id="en-cola"),
        pytest.param([run(name="Otro flujo")], id="solo-otro-flujo"),
        pytest.param([run(branch="dev")], id="solo-otra-rama"),
    ],
)
def test_ci_sin_terminar_espera_sin_tocar_nada(
    entorno: Entorno, runs: list[dict[str, Any]]
) -> None:
    antes = entorno.head()
    entorno.publicar("v2")

    resultado = entorno.ejecutar(runs=runs)

    assert resultado.returncode == 0
    assert resultado.stdout == ""
    assert entorno.head() == antes
    assert entorno.docker() == []


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_ci_sin_exito_no_despliega_y_lo_dice_una_vez(entorno: Entorno, conclusion: str) -> None:
    antes = entorno.head()
    entorno.publicar("v2")

    primera = entorno.ejecutar(runs=[run(conclusion=conclusion)])
    segunda = entorno.ejecutar(runs=[run(conclusion=conclusion)])

    assert primera.returncode == 0
    assert f"no pasó ({conclusion})" in primera.stdout
    assert segunda.stdout == ""
    assert entorno.head() == antes
    assert entorno.docker() == []


def test_ci_relanzada_en_verde_si_se_despliega(entorno: Entorno) -> None:
    nuevo = entorno.publicar("v2")
    entorno.ejecutar(runs=[run(conclusion="failure")])

    resultado = entorno.ejecutar(runs=[run(conclusion="failure"), run(attempt=2)])

    assert resultado.returncode == 0, resultado.stdout
    assert entorno.head() == nuevo


def test_cuenta_el_ultimo_intento_aunque_haya_uno_anterior_en_verde(entorno: Entorno) -> None:
    antes = entorno.head()
    entorno.publicar("v2")

    resultado = entorno.ejecutar(runs=[run(), run(conclusion="failure", attempt=2)])

    assert entorno.head() == antes
    assert "no pasó (failure)" in resultado.stdout


def test_un_commit_posterior_a_uno_rojo_si_se_despliega(entorno: Entorno) -> None:
    entorno.publicar("v2")
    entorno.ejecutar(runs=[run(conclusion="failure")])
    arreglo = entorno.publicar("v3")

    resultado = entorno.ejecutar()

    assert resultado.returncode == 0, resultado.stdout
    assert entorno.head() == arreglo


def test_ci_inconsultable_falla_y_lo_registra_una_vez(entorno: Entorno) -> None:
    entorno.publicar("v2")

    primera = entorno.ejecutar(gh_falla=True)
    segunda = entorno.ejecutar(gh_falla=True)

    assert primera.returncode == 1
    assert "no se pudo consultar la CI" in primera.stdout
    assert segunda.stdout == ""
    assert entorno.docker() == []


# --- Lo que lo detiene antes de tocar nada ------------------------------------------------------


def test_arbol_con_cambios_se_detiene_y_lo_registra_una_vez(entorno: Entorno) -> None:
    antes = entorno.head()
    entorno.publicar("v2")
    (entorno.produccion / "app.txt").write_text("arreglo a mano", encoding="utf-8")

    primera = entorno.ejecutar()
    segunda = entorno.ejecutar()

    assert primera.returncode == 1
    assert "cambios sin comitear" in primera.stdout
    assert segunda.returncode == 1
    assert segunda.stdout == ""
    assert entorno.head() == antes
    assert entorno.docker() == []


def test_simular_un_error_no_calla_el_de_la_pasada_real(entorno: Entorno) -> None:
    entorno.publicar("v2")
    (entorno.produccion / "app.txt").write_text("arreglo a mano", encoding="utf-8")

    simulada = entorno.ejecutar("--simular")
    real = entorno.ejecutar()

    assert "cambios sin comitear" in simulada.stdout
    assert "cambios sin comitear" in real.stdout


def test_archivo_suelto_que_el_commit_trae_se_detiene_antes_de_la_copia(
    entorno: Entorno,
) -> None:
    antes = entorno.head()
    (entorno.produccion / "nuevo.txt").write_text("a mano", encoding="utf-8")
    entorno.publicar("del repo", archivo="nuevo.txt")

    resultado = entorno.ejecutar()

    assert resultado.returncode == 1
    assert "sin seguimiento" in resultado.stdout
    assert "nuevo.txt" in resultado.stdout
    assert entorno.head() == antes
    assert entorno.docker() == []


def test_sin_fast_forward_no_despliega(entorno: Entorno) -> None:
    (entorno.produccion / "local.txt").write_text("commit solo en el servidor", encoding="utf-8")
    _git(entorno.produccion, "add", "local.txt")
    _git(entorno.produccion, "commit", "-qm", "local")
    antes = entorno.head()
    entorno.publicar("v2")

    resultado = entorno.ejecutar()

    assert resultado.returncode == 1
    assert "fast-forward" in resultado.stdout
    assert entorno.head() == antes
    assert entorno.docker() == []


@pytest.mark.parametrize("paso", ["backup --output", "verify --archive"])
def test_copia_fallida_pausa_avisa_y_no_insiste(entorno: Entorno, paso: str) -> None:
    antes = entorno.head()
    entorno.publicar("v2")
    avisos = entorno.tmp / "avisos.log"
    extra = {"CADENZA_DESPLIEGUE_AVISO": f"echo >> {avisos}"}

    primera = entorno.ejecutar(docker_falla=paso, extra=extra)
    segunda = entorno.ejecutar(docker_falla=paso, extra=extra)

    assert primera.returncode == 1
    assert "en pausa" in primera.stdout
    assert (entorno.estado / "pausado").exists()
    assert avisos.read_text(encoding="utf-8").count("Cadenza:") == 1
    assert segunda.stdout == ""
    assert entorno.head() == antes
    assert entorno.ups() == 0


# --- Vuelta atrás -------------------------------------------------------------------------------


def test_api_que_no_arranca_vuelve_al_anterior_avisa_y_no_reintenta(entorno: Entorno) -> None:
    antes = entorno.head()
    roto = entorno.publicar("v2")
    avisos = entorno.tmp / "avisos.log"
    extra = {"CADENZA_DESPLIEGUE_AVISO": f"echo >> {avisos}"}

    primera = entorno.ejecutar(malo=roto, extra=extra)
    segunda = entorno.ejecutar(malo=roto, extra=extra)

    assert primera.returncode == 1
    assert "vuelto a" in primera.stdout
    assert entorno.head() == antes
    assert entorno.ups() == 2
    assert "limpieza" not in entorno.llamadas()
    assert f"{roto[:7]} no arrancó" in avisos.read_text(encoding="utf-8")
    assert segunda.returncode == 0
    assert segunda.stdout == ""
    assert not (entorno.estado / "pausado").exists()


def test_si_tampoco_arranca_el_anterior_pausa_y_pide_restaurar_la_copia(
    entorno: Entorno,
) -> None:
    entorno.publicar("v2")

    resultado = entorno.ejecutar(docker_falla=" up -d --build")

    assert resultado.returncode == 1
    assert "ERROR GRAVE" in resultado.stdout
    assert "restaurar la copia cadenza-" in resultado.stdout
    assert (entorno.estado / "pausado").exists()
