"""Verifica la pureza del dominio: solo librería estándar, sin I/O ni ML."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN = {
    "music21",
    "torch",
    "onnxruntime",
    "fastapi",
    "pydantic",
    "numpy",
    "black",
    "ruff",
    "mypy",
    "pytest",
}


def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_domain_sources_exist() -> None:
    assert _source_files(), "no se encontraron fuentes del dominio"


def test_domain_uses_only_stdlib() -> None:
    offenders: dict[str, set[str]] = {}
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        external = _imported_roots(tree) - sys.stdlib_module_names - {"cadenza"}
        if external:
            offenders[str(path)] = external
    assert not offenders, f"el dominio importa módulos de terceros: {offenders}"


def test_domain_does_not_import_forbidden_modules() -> None:
    found: set[str] = set()
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found |= _imported_roots(tree)
    assert not (found & FORBIDDEN), f"módulos prohibidos en el dominio: {found & FORBIDDEN}"
