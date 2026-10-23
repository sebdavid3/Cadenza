"""La CLI de administración pide la contraseña sin eco si no se pasa (#156)."""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
from cadenza.api import cli
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)

SECRET = secrets.token_hex(32)


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+pysqlite:///{(tmp_path / 'cli.db').as_posix()}"
    monkeypatch.setenv("CADENZA_DATABASE_URL", url)
    monkeypatch.setenv("CADENZA_AUTH_SECRET_KEY", SECRET)
    create_schema(create_engine_for_url(url))
    return url


def _usernames(url: str) -> list[str]:
    with create_session_factory(create_engine_for_url(url))() as db:
        return [user.username for user in SqlAlchemyUserRepository(db).list()]


def test_create_investigator_asks_for_the_password_twice_without_echo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    url = _database(tmp_path, monkeypatch)
    password = secrets.token_urlsafe(12)
    prompts: list[str] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return password

    monkeypatch.setattr("getpass.getpass", fake_getpass)
    monkeypatch.setattr(sys, "argv", ["cli", "create-investigator", "--username", "admin"])

    cli.main()

    assert len(prompts) == 2
    assert _usernames(url) == ["admin"]
    assert password not in capsys.readouterr().out


def test_create_investigator_rejects_a_mistyped_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _database(tmp_path, monkeypatch)
    answers = iter([secrets.token_urlsafe(12), secrets.token_urlsafe(12)])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))
    monkeypatch.setattr(sys, "argv", ["cli", "create-investigator", "--username", "admin"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1
    assert _usernames(url) == []


def test_create_investigator_still_accepts_the_password_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _database(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cli",
            "create-investigator",
            "--username",
            "admin",
            "--password",
            secrets.token_urlsafe(12),
        ],
    )

    cli.main()

    assert _usernames(url) == ["admin"]
