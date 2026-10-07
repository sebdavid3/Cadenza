"""Test de arquitectura: packages/application no importa dependencias prohibidas.

Verifica estáticamente (vía AST) que la capa de aplicación
no importe FastAPI, SQLAlchemy, music21, homr ni onnxruntime (ADR-0009).
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_MODULES = {
    "fastapi",
    "sqlalchemy",
    "music21",
    "homr",
    "onnxruntime",
}


def test_ast_no_forbidden_imports() -> None:
    application_src = Path(__file__).resolve().parent.parent / "src"
    py_files = list(application_src.rglob("*.py"))
    assert py_files, "No se encontraron archivos en packages/application/src"

    violations: list[str] = []

    for file_path in py_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    if root_name in FORBIDDEN_MODULES:
                        violations.append(f"{file_path.name}:{node.lineno} importa {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_name = node.module.split(".")[0]
                if root_name in FORBIDDEN_MODULES:
                    violations.append(f"{file_path.name}:{node.lineno} importa de {node.module}")

    msg = "Violaciones de arquitectura detectadas en application:\n" + "\n".join(violations)
    assert not violations, msg


def test_application_package_loads_cleanly() -> None:
    import cadenza.application

    assert cadenza.application is not None
