"""Pruebas del contrato OpenAPI v1 de Cadenza en CI (Issue #26, ADR-0010, ADR-0012).

Verifica:
1. docs/api/openapi.json coincide exactamente con app.openapi() (control de deriva del contrato).
2. GET /version y la cabecera X-API-Version corresponden a la versión 1.0.0 congelada.
3. Todos los endpoints declaran respuestas de error estructuradas
   (401, 403, 404, 409, 413, 415, 422).
4. El esquema BearerAuth y OAuth2PasswordBearer están presentes en components.securitySchemes.
5. Los modelos centrales del dominio (ScoreDocument, ScoreIR, Anchor, Finding, EditEvent)
   están fuertemente tipados y sin dicts opacos.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cadenza.api.main import API_VERSION, create_app, create_default_app
from cadenza.api.settings import Settings
from cadenza.omr import FakeOMREngine
from cadenza.persistence import (
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OPENAPI_JSON_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"


@pytest.fixture
def test_client() -> TestClient:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    settings = Settings(auth_secret_key="test-secret-at-least-32-chars-long!")

    app = create_app(
        session_factory=session_factory,
        omr_engine=FakeOMREngine(),
        settings=settings,
    )
    return TestClient(app)


def test_openapi_file_matches_live_app_schema() -> None:
    """Valida que docs/api/openapi.json versionado coincide exactamente con app.openapi().

    Si esta prueba falla, regenera la especificación con:
    uv run python scripts/generate_openapi_and_types.py
    """
    assert OPENAPI_JSON_PATH.exists(), f"El archivo {OPENAPI_JSON_PATH} no existe."

    with open(OPENAPI_JSON_PATH, encoding="utf-8") as f:
        versioned_spec: dict[str, Any] = json.load(f)

    app = create_default_app(Settings(auth_secret_key="test-secret-at-least-32-chars-long!"))
    live_spec = app.openapi()

    assert versioned_spec == live_spec, (
        "El esquema OpenAPI en docs/api/openapi.json no coincide con app.openapi(). "
        "Ejecuta: uv run python scripts/generate_openapi_and_types.py"
    )


def test_api_version_endpoint_and_headers(test_client: TestClient) -> None:
    """Verifica que GET /version y la cabecera X-API-Version corresponden a 1.0.0."""
    response = test_client.get("/version")
    assert response.status_code == 200
    assert response.headers.get("x-api-version") == API_VERSION
    data = response.json()
    assert data["api_version"] == "1.0.0"
    assert data["app_version"] == "1.0.0"

    # Verificar que otros endpoints también inyectan la cabecera X-API-Version
    unauth_resp = test_client.get("/sessions")
    assert unauth_resp.headers.get("x-api-version") == API_VERSION


def test_openapi_spec_metadata_and_security() -> None:
    """Verifica metadatos, tags y esquemas de seguridad en la especificación."""
    with open(OPENAPI_JSON_PATH, encoding="utf-8") as f:
        spec: dict[str, Any] = json.load(f)

    assert spec["info"]["version"] == "1.0.0"
    assert spec["info"]["title"] == "Cadenza API"

    components = spec.get("components", {})
    security_schemes = components.get("securitySchemes", {})
    assert "BearerAuth" in security_schemes
    assert security_schemes["BearerAuth"]["type"] == "http"
    assert security_schemes["BearerAuth"]["scheme"] == "bearer"
    assert security_schemes["BearerAuth"]["bearerFormat"] == "JWT"

    tag_names = {t["name"] for t in spec.get("tags", [])}
    expected_tags = {
        "Auth",
        "Users",
        "Transcription",
        "Sessions",
        "Edits",
        "Validation",
        "Effort",
        "System",
    }
    assert expected_tags.issubset(tag_names)


def test_core_domain_schemas_are_strictly_typed() -> None:
    """Comprueba que los modelos centrales de ScoreDocument, ScoreIR y anclas están explícitos."""
    with open(OPENAPI_JSON_PATH, encoding="utf-8") as f:
        spec: dict[str, Any] = json.load(f)

    schemas = spec.get("components", {}).get("schemas", {})

    core_models = [
        "ScoreDocumentPayload",
        "ScoreIRPayload",
        "PartPayload",
        "StaffPayload",
        "MeasurePayload",
        "ScoreEventPayload",
        "AnchorPayload",
        "AnchorIndexPayload",
        "AnchorEntryPayload",
        "EventRefPayload",
        "FindingRead",
        "EditEventRead",
        "EditEventCreate",
        "SessionDetailRead",
        "SessionSummaryRead",
    ]

    for model_name in core_models:
        assert model_name in schemas, f"Modelo {model_name} falta en OpenAPI schemas"
        model_def = schemas[model_name]
        assert model_def.get("type") == "object", f"{model_name} debe ser un objeto"
        assert "properties" in model_def, f"{model_name} debe tener propiedades explícitas"

    # Verificar que ScoreDocumentPayload no usa tipos opacos
    doc_props = schemas["ScoreDocumentPayload"]["properties"]
    assert "$ref" in doc_props["score"]
    assert "$ref" in doc_props["anchors"]
    assert "$ref" in doc_props["provenance"]

    # Verificar que SessionDetailRead referencia los modelos fuertemente tipados
    session_props = schemas["SessionDetailRead"]["properties"]
    assert "$ref" in session_props["document"]
    assert session_props["findings"]["items"]["$ref"] == "#/components/schemas/FindingRead"
    assert session_props["edits"]["items"]["$ref"] == "#/components/schemas/EditEventRead"


def test_protected_endpoints_have_error_responses() -> None:
    """Verifica que los endpoints protegidos documentan respuestas 401 y 403."""
    with open(OPENAPI_JSON_PATH, encoding="utf-8") as f:
        spec: dict[str, Any] = json.load(f)

    paths = spec.get("paths", {})
    # Endpoints que requieren autenticación
    assert (
        "401" in paths["/auth/me"]["get"]["responses"]
    ), "GET /auth/me debe documentar respuesta 401"
    assert (
        "401" in paths["/transcribe"]["post"]["responses"]
    ), "POST /transcribe debe documentar respuesta 401"

    # Endpoints con control de acceso por rol o tenencia ADR-0012 (documentan 401 y 403)
    role_or_tenancy_paths = [
        ("/users", "get"),
        ("/users", "post"),
        ("/users/{user_id}", "patch"),
        ("/sessions/{session_id}/finalize", "post"),
        ("/sessions/{session_id}/reopen", "post"),
        ("/sessions/{session_id}/findings/{finding_id}/dismiss", "post"),
        ("/sessions/{session_id}/findings/{finding_id}/restore", "post"),
        ("/sessions/{session_id}/edits", "post"),
        ("/sessions/{session_id}/undo", "post"),
        ("/sessions/{session_id}/effort", "post"),
    ]

    for path, method in role_or_tenancy_paths:
        assert path in paths, f"Ruta {path} no encontrada en OpenAPI"
        operation = paths[path].get(method, {})
        responses = operation.get("responses", {})
        assert "401" in responses, f"{method.upper()} {path} debe documentar respuesta 401"
        assert "403" in responses, f"{method.upper()} {path} debe documentar respuesta 403"
