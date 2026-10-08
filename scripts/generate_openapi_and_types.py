"""Generador del contrato OpenAPI v1 y tipos TypeScript para Cadenza.

Exporta docs/api/openapi.json directamente desde la aplicación FastAPI
y genera apps/web/src/types.ts para sincronizar el contrato tipado con el frontend.
(Issue #26, ADR-0010, ARCHITECTURE.md §6.4).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Asegurar secreto para inicialización si no existe en entorno
if "CADENZA_AUTH_SECRET_KEY" not in os.environ:
    os.environ["CADENZA_AUTH_SECRET_KEY"] = "dev-secret-key-at-least-32-bytes-long!"

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_JSON_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"
TYPES_TS_PATH = REPO_ROOT / "apps" / "web" / "src" / "types.ts"


def schema_to_ts_type(
    schema: dict[str, Any], schemas: dict[str, Any], indent_level: int = 1
) -> str:
    """Convierte una definición de JSON Schema a una expresión de tipo TypeScript."""
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return ref_name

    if "anyOf" in schema:
        variants = [schema_to_ts_type(v, schemas, indent_level) for v in schema["anyOf"]]
        unique_variants: list[str] = []
        for var in variants:
            if var not in unique_variants:
                unique_variants.append(var)
        return " | ".join(unique_variants)

    schema_type = schema.get("type")

    if schema_type == "null":
        return "null"

    if "enum" in schema:
        return " | ".join(f'"{val}"' for val in schema["enum"])

    if schema_type == "string":
        return "string"

    if schema_type in ("integer", "number"):
        return "number"

    if schema_type == "boolean":
        return "boolean"

    if schema_type == "array":
        items = schema.get("items")
        if items:
            item_type = schema_to_ts_type(items, schemas, indent_level)
            if " | " in item_type:
                return f"({item_type})[]"
            return f"{item_type}[]"
        return "unknown[]"

    if schema_type == "object":
        properties = schema.get("properties")
        additional_props = schema.get("additionalProperties")
        if not properties:
            if additional_props is True or additional_props == {}:
                return "Record<string, unknown>"
            if isinstance(additional_props, dict):
                val_type = schema_to_ts_type(additional_props, schemas, indent_level)
                return f"Record<string, {val_type}>"
            return "Record<string, unknown>"

        req = set(schema.get("required", []))
        lines = ["{"]
        indent = "  " * indent_level
        for prop_name, prop_def in properties.items():
            opt = "" if prop_name in req else "?"
            t = schema_to_ts_type(prop_def, schemas, indent_level + 1)
            lines.append(f"{indent}  {prop_name}{opt}: {t};")
        lines.append(f"{indent}}}")
        return "\n".join(lines)

    return "unknown"


def generate_typescript_definitions(openapi: dict[str, Any]) -> str:
    """Genera el código TypeScript para los modelos tipados de OpenAPI."""
    schemas = openapi.get("components", {}).get("schemas", {})

    lines: list[str] = [
        "/**",
        " * Tipos TypeScript del contrato API v1 de Cadenza.",
        " * Generado automáticamente a partir de docs/api/openapi.json (OpenAPI 3.1 / FastAPI).",
        " * Ejecutar: uv run python scripts/generate_openapi_and_types.py para regenerar.",
        " */",
        "",
        "// --- Primitivos y tipos base del dominio ---",
        "export type BBox = [number, number, number, number];",
        'export type EventKind = "note" | "rest" | "clef" | "key" | "time";',
        'export type Severity = "info" | "warning" | "error";',
        'export type UserRole = "transcriptor" | "investigador";',
        "",
    ]

    for schema_name in sorted(schemas.keys()):
        if schema_name.startswith("Body_"):
            continue
        schema_def = schemas[schema_name]
        description = schema_def.get("description", "")
        if description:
            lines.append("/**")
            for desc_line in description.strip().splitlines():
                lines.append(f" * {desc_line}")
            lines.append(" */")

        if "enum" in schema_def:
            enum_vals = " | ".join(f'"{v}"' for v in schema_def["enum"])
            lines.append(f"export type {schema_name} = {enum_vals};")
            lines.append("")
            continue

        if schema_def.get("type") == "object" and "properties" in schema_def:
            req = set(schema_def.get("required", []))
            lines.append(f"export interface {schema_name} {{")
            for prop_name, prop_def in schema_def["properties"].items():
                prop_desc = prop_def.get("description")
                if prop_desc:
                    lines.append(f"  /** {prop_desc} */")
                opt = "" if prop_name in req else "?"
                # Personalizaciones de tipos del dominio para ergonomía estricta
                if (
                    schema_name
                    in ("AnchorPayload", "Anchor", "EventRefPayload", "ScoreEventPayload")
                    and prop_name == "bbox"
                ):
                    ts_type = "BBox | null"
                elif (
                    schema_name in ("ScoreEventPayload", "EventRefPayload") and prop_name == "kind"
                ):
                    ts_type = "EventKind"
                elif schema_name == "FindingRead" and prop_name == "severity":
                    ts_type = "Severity"
                elif schema_name in ("UserRead", "UserCreate") and prop_name == "role":
                    ts_type = "UserRole"
                elif schema_name in ("EditEventRead", "EditEventCreate") and prop_name == "op":
                    ts_type = "EditOp | string"
                else:
                    ts_type = schema_to_ts_type(prop_def, schemas, indent_level=1)

                # Asegurar propiedades centrales definidas sin undefined
                if (
                    schema_name == "ScoreEventPayload"
                    and prop_name
                    in (
                        "voice",
                        "pitch",
                        "duration_beats",
                        "bbox",
                        "confidence",
                        "ir_handle",
                    )
                ) or (schema_name == "AnchorPayload" and prop_name in ("bbox", "confidence")):
                    opt = ""

                lines.append(f"  {prop_name}{opt}: {ts_type};")
            lines.append("}")
            lines.append("")
        else:
            ts_type = schema_to_ts_type(schema_def, schemas, indent_level=1)
            lines.append(f"export type {schema_name} = {ts_type};")
            lines.append("")

    lines.extend(
        [
            "// --- Alias ergonómicos de compatibilidad para el Frontend ---",
            "export type Anchor = AnchorPayload;",
            "export type ScoreEvent = ScoreEventPayload;",
            "export type TimeSignature = TimeSignaturePayload;",
            "export type Clef = ClefPayload;",
            "export type KeySignature = KeySignaturePayload;",
            "export type Measure = MeasurePayload;",
            "export type Staff = StaffPayload;",
            "export type Part = PartPayload;",
            "export type ScoreIR = ScoreIRPayload;",
            "export type EventRef = EventRefPayload;",
            "export type AnchorEntry = AnchorEntryPayload;",
            "export type AnchorIndex = AnchorIndexPayload;",
            "export type Provenance = ProvenancePayload;",
            "export type ScoreDocument = ScoreDocumentPayload;",
            "export type Finding = FindingRead;",
            "export type EditEvent = EditEventRead;",
            "export type SessionDetail = SessionDetailRead;",
            "export type SessionSummary = SessionSummaryRead;",
            "export type UserProfile = UserRead;",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    from cadenza.api.main import create_default_app

    print("Construyendo aplicación FastAPI...")
    app = create_default_app()
    spec = app.openapi()

    OPENAPI_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    TYPES_TS_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Escribiendo especificación OpenAPI en {OPENAPI_JSON_PATH}...")
    with open(OPENAPI_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Generando tipos TypeScript en {TYPES_TS_PATH}...")
    ts_code = generate_typescript_definitions(spec)
    with open(TYPES_TS_PATH, "w", encoding="utf-8") as f:
        f.write(ts_code)

    print("¡Generación completada exitosamente!")


if __name__ == "__main__":
    main()
