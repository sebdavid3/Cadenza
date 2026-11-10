"""Pruebas de `deploy/desplegar.sh`, el despliegue manual de dev en un comando (#382).

Como las de `test_despliegue_continuo.py`: un remoto `origin` y un clon de «producción» con git de
verdad, y delante del PATH un `docker` que apunta cada orden (y falla en la que pida la prueba) y un
`curl` que responde sano salvo cuando el commit desplegado es el marcado como roto.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "desplegar.sh"

FAKE_DOCKER = """#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
if [ -n "${FAKE_DOCKER_FALLA:-}" ]; then
    case " $* " in
        *"$FAKE_DOCKER_FALLA"*) exit 1 ;;
    esac
fi
exit 0
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
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def _ejecutable(ruta: Path, contenido: str) -> None:
    ruta.write_text(contenido, encoding="utf-8", newline="\n")
    ruta.chmod(0o755)


@dataclass
class Entorno:
    tmp: Path
    desarrollo: Path
    produccion: Path
    registro: Path
    bin: Path

    def publicar(self, texto: str) -> str:
        """Un commit nuevo en origin/dev, como la fusión de un PR."""
        (self.desarrollo / "app.txt").write_text(texto, encoding="utf-8")
        _git(self.desarrollo, "commit", "-qam", texto)
        _git(self.desarrollo, "push", "-q", "origin", "dev")
        return _git(self.desarrollo, "rev-parse", "HEAD")

    def desplegar(
        self, esperado: str, *, docker_falla: str = "", malo: str = ""
    ) -> subprocess.CompletedProcess[str]:
        env = {
            **{k: v for k, v in os.environ.items() if k != "CADENZA_WEB_PORT"},
            **GIT_ENV,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "CADENZA_DESPLIEGUE_DIR": str(self.produccion),
            "CADENZA_DESPLIEGUE_ESPERA": "1",
            "CADENZA_DESPLIEGUE_INTERVALO": "0.2",
            "FAKE_LOG": str(self.registro),
            "FAKE_DOCKER_FALLA": docker_falla,
            "FAKE_MALO": malo,
        }
        # Como en el servidor: el guion llega por la entrada estándar (`ssh … "sh -s <commit>"`).
        return subprocess.run(
            ["sh", "-s", esperado],
            input=SCRIPT.read_text(encoding="utf-8"),
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


@pytest.fixture()
def entorno(tmp_path: Path) -> Entorno:
    if shutil.which("sh") is None:
        pytest.skip("las pruebas necesitan sh")
    origen = tmp_path / "origen.git"
    desarrollo = tmp_path / "desarrollo"
    produccion = tmp_path / "produccion"
    binarios = tmp_path / "bin"
    binarios.mkdir()
    _ejecutable(binarios / "docker", FAKE_DOCKER)
    _ejecutable(binarios / "curl", FAKE_CURL)

    _git(tmp_path, "init", "-q", "--bare", "-b", "dev", str(origen))
    _git(tmp_path, "clone", "-q", str(origen), str(desarrollo))
    _git(desarrollo, "switch", "-q", "-c", "dev")
    (desarrollo / "deploy").mkdir()
    _ejecutable(desarrollo / "deploy" / "limpieza-docker.sh", FAKE_LIMPIEZA)
    (desarrollo / "app.txt").write_text("v1", encoding="utf-8")
    _git(desarrollo, "add", "deploy", "app.txt")
    _git(desarrollo, "commit", "-qm", "v1")
    _git(desarrollo, "push", "-q", "origin", "dev")
    _git(tmp_path, "clone", "-q", "-b", "dev", str(origen), str(produccion))
    return Entorno(tmp_path, desarrollo, produccion, tmp_path / "llamadas.log", binarios)


def test_despliega_el_commit_esperado_con_copia_verificada_y_salud(entorno: Entorno) -> None:
    nuevo = entorno.publicar("v2")

    resultado = entorno.desplegar(nuevo[:7])

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert entorno.head() == nuevo
    llamadas = entorno.llamadas()
    orden = [
        next(i for i, c in enumerate(llamadas) if trozo in c)
        for trozo in (
            "backup --output",
            "verify --archive",
            "up -d --build",
            "build backup",
            "limpieza",
            "curl http://127.0.0.1:8380/api/health",
        )
    ]
    # La copia y su verificación antes de tocar nada; la salud, al final.
    assert orden == sorted(orden)
    assert "sana tras" in resultado.stdout


def test_sin_el_commit_esperado_no_hace_nada(entorno: Entorno) -> None:
    resultado = entorno.desplegar("")

    assert resultado.returncode == 64
    assert entorno.llamadas() == []


def test_si_origin_dev_no_es_el_esperado_no_hace_nada(entorno: Entorno) -> None:
    antes = entorno.head()
    entorno.publicar("v2")

    resultado = entorno.desplegar("0123abc")

    assert resultado.returncode == 1
    assert "no se despliega" in resultado.stdout
    assert entorno.head() == antes
    assert entorno.llamadas() == []


def test_con_el_arbol_del_servidor_sucio_no_hace_nada(entorno: Entorno) -> None:
    antes = entorno.head()
    nuevo = entorno.publicar("v2")
    (entorno.produccion / "app.txt").write_text("arreglo a mano", encoding="utf-8")

    resultado = entorno.desplegar(nuevo)

    assert resultado.returncode == 1
    assert "cambios sin comitear" in resultado.stdout
    assert entorno.head() == antes
    assert entorno.llamadas() == []


@pytest.mark.parametrize("falla", ["backup --output", "verify --archive"])
def test_sin_copia_verificada_no_toca_el_codigo(entorno: Entorno, falla: str) -> None:
    antes = entorno.head()
    nuevo = entorno.publicar("v2")

    resultado = entorno.desplegar(nuevo, docker_falla=falla)

    assert resultado.returncode != 0
    assert entorno.head() == antes
    assert not any("up -d --build" in c for c in entorno.llamadas())


def test_si_la_api_no_queda_sana_lo_dice_y_sale_con_2(entorno: Entorno) -> None:
    nuevo = entorno.publicar("v2")

    resultado = entorno.desplegar(nuevo, malo=nuevo)

    assert resultado.returncode == 2
    assert "no responde sana" in resultado.stdout
    assert "la copia previa es cadenza-" in resultado.stdout
    # Sin vuelta atrás automática: queda el commit nuevo, para mirarlo.
    assert entorno.head() == nuevo


def test_los_guiones_de_shell_se_sacan_con_lf_tambien_en_windows() -> None:
    # Con CRLF, `sh -s < deploy/desplegar.sh` fallaría en el servidor (`.gitattributes`).
    for guion in SCRIPT.parent.glob("*.sh"):
        assert b"\r" not in guion.read_bytes(), guion.name
