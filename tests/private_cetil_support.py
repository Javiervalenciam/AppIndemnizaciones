from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    cetil_result_to_dict,
)

PRIVATE_SNAPSHOT_SCHEMA_VERSION = 1


def canonical_cetil_result(result: CetilExtractionResult) -> dict[str, Any]:
    """Return all requested regression fields without full-page or row source text."""
    payload = cetil_result_to_dict(result)
    payload.pop("texto_paginas", None)
    return _without_raw_text(payload)


def private_snapshot(
    pdf_path: Path,
    replacements: dict[str, str] | None = None,
) -> dict[str, Any]:
    content = pdf_path.read_bytes()
    result = CetilExtractor().extract_from_bytes(content)
    canonical = canonical_cetil_result(result)
    return {
        "schema_version": PRIVATE_SNAPSHOT_SCHEMA_VERSION,
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "result": apply_exact_replacements(canonical, replacements or {}),
    }


def apply_exact_replacements(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: apply_exact_replacements(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [apply_exact_replacements(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def suggested_replacements(payload: dict[str, Any]) -> dict[str, str]:
    """Build a private sidecar; exact source values never enter the tracked snapshot."""
    suggestions: list[tuple[Any, str]] = []
    metadata = payload.get("metadata") or {}
    worker = payload.get("trabajador") or {}
    employer = payload.get("entidad_empleadora") or {}

    suggestions.extend(
        [
            (metadata.get("numero_cetil"), "<NUMERO_CETIL>"),
            (worker.get("documento"), "<DOCUMENTO>"),
            (worker.get("primer_apellido"), "<PRIMER_APELLIDO>"),
            (worker.get("segundo_apellido"), "<SEGUNDO_APELLIDO>"),
            (worker.get("primer_nombre"), "<PRIMER_NOMBRE>"),
            (worker.get("segundo_nombre"), "<SEGUNDO_NOMBRE>"),
            (worker.get("nombre_completo"), "<NOMBRE_COMPLETO>"),
            (worker.get("fecha_nacimiento"), "<FECHA_NACIMIENTO>"),
            (employer.get("nombre_entidad_empleadora"), "<ENTIDAD_EMPLEADORA>"),
            (employer.get("nit_entidad_empleadora"), "<NIT_ENTIDAD_EMPLEADORA>"),
            (payload.get("entidad_certificadora"), "<ENTIDAD_CERTIFICADORA>"),
        ]
    )
    for index, period in enumerate(payload.get("periodos_certificados", []), start=1):
        suggestions.append(
            (period.get("entidad_responsable"), f"<ENTIDAD_RESPONSABLE_{index:02d}>")
        )

    replacements: dict[str, str] = {}
    for raw_value, replacement in suggestions:
        if isinstance(raw_value, str) and raw_value:
            replacements.setdefault(raw_value, replacement)
    return replacements


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_raw_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_raw_text(item)
            for key, item in value.items()
            if key != "raw_text"
        }
    if isinstance(value, list):
        return [_without_raw_text(item) for item in value]
    return value
