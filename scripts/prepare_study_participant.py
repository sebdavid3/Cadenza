"""Prepara la cuenta y las sesiones de un participante del estudio (#249, protocolo §2.4 y §5).

Antes de cada participante, el investigador ejecuta, desde la carpeta del repositorio y con el
banco ya regenerado (`scripts/build_study_bank.py`):

    uv run --no-sync python -P scripts/prepare_study_participant.py P01 \\
        --api-url https://r2d2.tailcacb19.ts.net/api --investigator <su usuario>

La orden usa solo el contrato v1, como la web:

1. Entra como investigador y da de alta la cuenta `P01` (transcriptor, no del registro: así entra
   en `exp_10`, ADR-0022). Si ya existe, comprueba que es una cuenta del estudio y no la toca.
2. Entra como el participante y transcribe con HOMR el calentamiento (§5.2) y sus cuatro bloques
   según la matriz (`estudio.matriz` de `docs/experimentos/banco_de_partituras.json`), con su
   condición y su `test_score_id`, a su nombre (ADR-0012).
3. El participante ve en su listado «Calentamiento» y «Partitura 1» a «Partitura 4», en ese
   orden, con un nombre de archivo neutro: nada de la condición ni de la partitura de prueba.

Es idempotente: una sesión que ya existe con su `test_score_id` y su condición no se repite, y
tras un corte basta con volver a ejecutarla. Si el proxy corta una transcripción larga (Nginx
espera 60 s), la API la termina y la guarda igualmente (ADR-0024): la orden espera a que aparezca
en el listado antes de seguir, para no transcribir dos veces el mismo bloque. Las contraseñas se
piden sin eco y no se imprimen, tampoco en los mensajes de error.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "docs" / "experimentos" / "banco_de_partituras.json"
REGENERATE = "uv run --no-sync python -P scripts/build_study_bank.py"
# Lo que espera el cliente a una transcripción. Por la URL pública, Nginx corta antes (60 s,
# `deploy/nginx/cadenza-proxy.conf`), pero la API la termina y la guarda (ADR-0024).
TRANSCRIBE_TIMEOUT_S = 600.0
# Tras un corte del proxy, cuánto se espera a que la sesión aparezca y cada cuánto se mira.
CUT_WAIT_S = 600.0
CUT_POLL_S = 10.0
MIN_PASSWORD_LENGTH = 8


class PrepareError(Exception):
    """La preparación no puede seguir; el mensaje dice por qué y qué hacer."""


@dataclass(frozen=True)
class PlannedSession:
    """Una sesión del participante: el calentamiento (bloque 0) o uno de sus cuatro bloques."""

    block: int
    test_score_id: str
    condition: str
    title: str
    filename: str
    image: Path
    instruments: tuple[str, ...]


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return manifest


def plan_sessions(
    manifest: dict[str, Any], participant: str, bank_dir: Path
) -> list[PlannedSession]:
    """El calentamiento y los cuatro bloques de `participant`, en el orden del protocolo.

    Comprueba antes de tocar la API que cada imagen del banco existe y tiene el sha256 del
    manifiesto: si no, hay que regenerar el banco.
    """

    study = manifest["estudio"]
    matrix: dict[str, list[dict[str, str]]] = study["matriz"]
    if participant not in matrix:
        known = ", ".join(sorted(matrix))
        raise PrepareError(f"El participante {participant} no está en la matriz ({known}).")
    scores = {entry["id"]: entry for entry in manifest["partituras"]}

    warmup = study["calentamiento"]
    wanted = [(0, warmup["partitura"], warmup["condicion"], warmup["titulo"], warmup["archivo"])]
    for block, assignment in enumerate(matrix[participant], start=1):
        wanted.append(
            (
                block,
                assignment["partitura"],
                assignment["condicion"],
                study["titulo_bloque"].format(bloque=block),
                study["archivo_bloque"].format(bloque=block),
            )
        )

    plan: list[PlannedSession] = []
    problems: list[str] = []
    for block, score_id, condition, title, filename in wanted:
        entry = scores[score_id]
        image = bank_dir / entry["salida"]["imagen"]
        if not image.is_file():
            problems.append(f"falta {image.name}")
        elif hashlib.sha256(image.read_bytes()).hexdigest() != entry["sha256"]["imagen"]:
            problems.append(f"{image.name} no tiene el sha256 del manifiesto")
        plan.append(
            PlannedSession(
                block=block,
                test_score_id=score_id,
                condition=condition,
                title=title,
                filename=filename,
                image=image,
                instruments=tuple(entry.get("instrumentos", ())),
            )
        )
    if problems:
        raise PrepareError(
            f"El banco de {bank_dir} no está listo ({'; '.join(problems)}). "
            f"Regenéralo con `{REGENERATE}`."
        )
    return plan


def _detail(response: httpx.Response) -> str:
    """El código y el motivo de un error de la API, sin lo que se envió.

    Un 422 de FastAPI repite en `input` el valor rechazado, que puede ser una contraseña: de cada
    error solo se muestran el campo y el mensaje.
    """
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, list):
        reasons = []
        for item in detail:
            if isinstance(item, dict):
                field = ".".join(str(part) for part in item.get("loc", ())[1:])
                message = str(item.get("msg", ""))
                reasons.append(f"{field}: {message}" if field else message)
        detail = "; ".join(reasons)
    elif not isinstance(detail, str):
        detail = None
    return f"HTTP {response.status_code}: {detail}" if detail else f"HTTP {response.status_code}"


def _login(
    client: httpx.Client, username: str, password: str, wrong_credentials: str
) -> dict[str, str]:
    response = client.post("/auth/login", data={"username": username, "password": password})
    if response.status_code == 401:
        raise PrepareError(wrong_credentials)
    if response.status_code != 200:
        raise PrepareError(f"No se pudo entrar como {username} ({_detail(response)}).")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ensure_account(
    client: httpx.Client,
    investigator: dict[str, str],
    participant: str,
    participant_password: Callable[[bool], str],
    report: Callable[[str], None],
) -> str:
    """Da de alta la cuenta si no existe y devuelve su contraseña."""

    response = client.get("/users", headers=investigator)
    if response.status_code == 403:
        raise PrepareError("La cuenta con la que se entra no es de investigador.")
    if response.status_code != 200:
        raise PrepareError(f"No se pudieron listar las cuentas ({_detail(response)}).")
    existing = next((u for u in response.json() if u["username"] == participant), None)

    if existing is None:
        password = participant_password(True)
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PrepareError(
                f"La contraseña de {participant} debe tener al menos {MIN_PASSWORD_LENGTH} "
                "caracteres: no se crea la cuenta."
            )
        created = client.post(
            "/users",
            json={"username": participant, "password": password, "role": "transcriptor"},
            headers=investigator,
        )
        if created.status_code != 201:
            raise PrepareError(f"No se pudo crear la cuenta {participant} ({_detail(created)}).")
        report(f"Cuenta {participant}: creada (transcriptor).")
        return password

    if existing["role"] != "transcriptor" or existing.get("self_registered"):
        raise PrepareError(
            f"La cuenta {participant} ya existe y no es una cuenta de transcriptor creada por el "
            "investigador: no sirve para el estudio."
        )
    if not existing["active"]:
        raise PrepareError(
            f"La cuenta {participant} está desactivada: actívala en /cuentas antes de seguir."
        )
    report(f"Cuenta {participant}: ya existía.")
    return participant_password(False)


def _study_sessions(client: httpx.Client, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Las sesiones del participante con partitura de prueba, como las ve: la más reciente
    primero."""
    response = client.get("/sessions", params={"limit": 100}, headers=headers)
    if response.status_code != 200:
        raise PrepareError(f"No se pudieron listar las sesiones ({_detail(response)}).")
    return [s for s in response.json() if s.get("test_score_id")]


def _by_score(listed: Sequence[dict[str, Any]], participant: str) -> dict[str, dict[str, Any]]:
    existing: dict[str, dict[str, Any]] = {}
    for session in listed:
        if session["test_score_id"] in existing:
            raise PrepareError(
                f"{participant} tiene más de una sesión de {session['test_score_id']}: "
                "revísalas antes de seguir."
            )
        existing[session["test_score_id"]] = session
    return existing


def _check_existing(
    plan: Sequence[PlannedSession], existing: dict[str, dict[str, Any]], participant: str
) -> None:
    """Lo que ya existe debe coincidir con la matriz y permitir seguir sin romper el orden."""

    for planned in plan:
        session = existing.get(planned.test_score_id)
        if session is not None and session["condition"] != planned.condition:
            raise PrepareError(
                f"{participant} ya tiene una sesión de {planned.test_score_id} en condición "
                f"{session['condition']}, y la matriz pide {planned.condition}. Revísala antes "
                "de seguir: no se crea nada."
            )
    # Se crean del último bloque al calentamiento (el listado va del más reciente al más
    # antiguo): lo que ya existe tiene que ser el principio de ese orden.
    creation = list(reversed(plan))
    present = [planned.test_score_id in existing for planned in creation]
    if present != sorted(present, reverse=True):
        raise PrepareError(
            f"Las sesiones que ya tiene {participant} no permiten crear las que faltan en el orden "
            "de sus bloques: no se crea nada."
        )


def _verify(
    listed: Sequence[dict[str, Any]], plan: Sequence[PlannedSession], participant: str
) -> None:
    """Al acabar: una sesión por partitura, con su condición y su título, y en el listado en el
    orden de los bloques (el calentamiento arriba)."""

    existing = _by_score(listed, participant)
    for planned in plan:
        session = existing.get(planned.test_score_id)
        if session is None:
            raise PrepareError(f"Falta la sesión de {planned.test_score_id} de {participant}.")
        if (session["condition"], session["title"]) != (planned.condition, planned.title):
            raise PrepareError(
                f"La sesión de {planned.test_score_id} de {participant} no tiene la condición o "
                "el título de la matriz."
            )
    wanted = {planned.test_score_id for planned in plan}
    order = [s["test_score_id"] for s in listed if s["test_score_id"] in wanted]
    if order != [planned.test_score_id for planned in plan]:
        raise PrepareError(f"El listado de {participant} no queda en el orden de sus bloques.")


def _transcribe(
    client: httpx.Client,
    headers: dict[str, str],
    planned: PlannedSession,
    *,
    wait_s: float,
    poll_s: float,
    sleep: Callable[[float], None],
) -> tuple[dict[str, Any], bool]:
    """Transcribe una sesión; devuelve su resumen y si llegó tras un corte del proxy.

    Un 502 o un 504 del proxy, o una respuesta que no llega, no dicen que la transcripción
    fallara: la API la termina y la guarda aunque el cliente se haya ido (ADR-0024). Se espera a
    que aparezca en el listado, en vez de pedirla otra vez y crear dos.
    """

    data: dict[str, Any] = {
        "condition": planned.condition,
        "test_score_id": planned.test_score_id,
        "title": planned.title,
    }
    if planned.instruments:
        data["instruments"] = list(planned.instruments)
    response: httpx.Response | None
    try:
        response = client.post(
            "/transcribe",
            files={"file": (planned.filename, planned.image.read_bytes(), "image/png")},
            data=data,
            headers=headers,
        )
    except httpx.TransportError:
        response = None
    if response is not None and response.status_code == 201:
        created: dict[str, Any] = response.json()
        return created, False
    if response is not None and response.status_code not in (502, 504):
        raise PrepareError(
            f"{planned.title} ({planned.test_score_id}): la transcripción falló "
            f"({_detail(response)}). Vuelve a ejecutar la orden: las sesiones ya creadas no se "
            "repiten."
        )

    waited = 0.0
    while waited < wait_s:
        sleep(poll_s)
        waited += poll_s
        found = client.get(
            "/sessions",
            params={"test_score_id": planned.test_score_id, "limit": 100},
            headers=headers,
        )
        if found.status_code == 200 and found.json():
            session: dict[str, Any] = found.json()[0]
            return session, True
    raise PrepareError(
        f"{planned.title} ({planned.test_score_id}): el proxy cortó la transcripción y no "
        f"apareció en {wait_s:.0f} s. Puede seguir en curso: espera unos minutos y vuelve a "
        "ejecutar la orden, que no repite lo que ya exista."
    )


def prepare_participant(
    client: httpx.Client,
    *,
    participant: str,
    investigator: str,
    investigator_password: str,
    participant_password: Callable[[bool], str],
    plan: Sequence[PlannedSession],
    report: Callable[[str], None],
    limit: int | None = None,
    wait_s: float = CUT_WAIT_S,
    poll_s: float = CUT_POLL_S,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Prepara la cuenta y las sesiones de `participant` (ver el docstring del módulo).

    `participant_password(nueva)` da la contraseña de la cuenta; `nueva` dice si la cuenta se va
    a crear, para pedirla dos veces. `limit` corta tras ese número de transcripciones (pruebas);
    `wait_s`, `poll_s` y `sleep` gobiernan la espera tras un corte del proxy.
    """

    investigator_headers = _login(
        client,
        investigator,
        investigator_password,
        f"No se pudo entrar como {investigator}: usuario o contraseña incorrectos.",
    )
    password = _ensure_account(
        client, investigator_headers, participant, participant_password, report
    )
    headers = _login(
        client,
        participant,
        password,
        f"No se pudo entrar como {participant}: la contraseña no es la de la cuenta "
        "(restablécela en /cuentas).",
    )

    existing = _by_score(_study_sessions(client, headers), participant)
    _check_existing(plan, existing, participant)

    transcribed = 0
    for planned in reversed(plan):
        label = (
            f"Bloque {planned.block} · {planned.title} · {planned.test_score_id} · "
            f"{planned.condition}"
        )
        if planned.test_score_id in existing:
            session = existing[planned.test_score_id]
            line = (
                f"{label}: ya existía ({session['session_id']}, {session['status']}, "
                f"{session['edits_count']} ediciones)."
            )
            if session["edits_count"]:
                line += " Ojo: ya tiene ediciones; si no son del participante, revísala."
            report(line)
            continue
        if limit is not None and transcribed >= limit:
            return
        result, after_cut = _transcribe(
            client, headers, planned, wait_s=wait_s, poll_s=poll_s, sleep=sleep
        )
        transcribed += 1
        report(
            f"{label}: creada ({result['session_id']}, {result['findings_count']} posibles "
            f"errores){' tras un corte del proxy' if after_cut else ''}."
        )

    _verify(_study_sessions(client, headers), plan, participant)
    report(f"{participant}: listo, con el calentamiento y sus cuatro bloques.")


def _ask_password(participant: str) -> Callable[[bool], str]:
    def ask(new_account: bool) -> str:
        if not new_account:
            return getpass.getpass(f"Contraseña de {participant}: ")
        for _attempt in range(3):
            password = getpass.getpass(
                f"Contraseña nueva para {participant} (mínimo {MIN_PASSWORD_LENGTH} caracteres): "
            )
            if len(password) < MIN_PASSWORD_LENGTH:
                print(f"Tiene menos de {MIN_PASSWORD_LENGTH} caracteres.", file=sys.stderr)
                continue
            if getpass.getpass("Repítela: ") != password:
                raise PrepareError("Las dos contraseñas no coinciden.")
            return password
        raise PrepareError("No se dio una contraseña válida.")

    return ask


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Crea la cuenta de un participante del estudio y sus sesiones: el calentamiento y "
            "sus cuatro bloques según la matriz del protocolo (#249)."
        )
    )
    parser.add_argument("participant", help="Código del participante, de P01 a P08")
    parser.add_argument(
        "--api-url",
        required=True,
        help="URL base de la API, por ejemplo https://r2d2.tailcacb19.ts.net/api",
    )
    parser.add_argument("--investigator", required=True, help="Usuario investigador")
    parser.add_argument(
        "--bank-dir",
        default=None,
        help="Carpeta del banco regenerado (por defecto, la del manifiesto: banco_estudio)",
    )
    args = parser.parse_args(argv)

    manifest = load_manifest()
    bank_dir = Path(args.bank_dir) if args.bank_dir else REPO_ROOT / manifest["salida"]
    try:
        plan = plan_sessions(manifest, args.participant, bank_dir)
        investigator_password = getpass.getpass(f"Contraseña de {args.investigator}: ")
        with httpx.Client(base_url=args.api_url, timeout=TRANSCRIBE_TIMEOUT_S) as client:
            prepare_participant(
                client,
                participant=args.participant,
                investigator=args.investigator,
                investigator_password=investigator_password,
                participant_password=_ask_password(args.participant),
                plan=plan,
                report=print,
            )
    except (PrepareError, httpx.HTTPError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
