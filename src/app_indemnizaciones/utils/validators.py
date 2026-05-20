from __future__ import annotations

from datetime import date
from typing import Any

from app_indemnizaciones.services.period_normalizer import (
    FUENTES_PERMITIDAS,
    normalize_period_row,
    parse_ibl_decimal,
)


def _parse_iso_date(value: str, label: str, errors: list[str]) -> date | None:
    if not value:
        errors.append(f"{label} obligatoria")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} debe tener formato AAAA-MM-DD")
        return None


def _append_message(row: dict[str, str], message: str) -> None:
    current = row.get("errores", "")
    row["errores"] = f"{current}; {message}" if current else message


def validate_period_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = normalize_period_row(row)
    errors: list[str] = []
    warnings: list[str] = []

    fecha_inicio = _parse_iso_date(normalized["fecha_inicio"], "fecha_inicio", errors)
    fecha_fin = _parse_iso_date(normalized["fecha_fin"], "fecha_fin", errors)
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        errors.append("fecha_inicio no puede ser posterior a fecha_fin")

    ibl_text = normalized["ibl_reportado"]
    if not ibl_text:
        errors.append("IBL reportado requerido")
    else:
        try:
            ibl = parse_ibl_decimal(ibl_text)
            if ibl <= 0:
                errors.append("ibl_reportado debe ser mayor que cero")
        except ValueError:
            errors.append("ibl_reportado debe ser numérico")

    if normalized["fuente"] not in FUENTES_PERMITIDAS:
        errors.append("fuente debe ser manual, cetil o importado")

    if not normalized["cargo"]:
        warnings.append("cargo vacío")
    if not normalized["entidad"]:
        warnings.append("entidad vacía")

    messages = errors + warnings
    if errors:
        normalized["estado_validacion"] = "ERROR"
    elif warnings:
        normalized["estado_validacion"] = "ADVERTENCIA"
    else:
        normalized["estado_validacion"] = "OK"
    normalized["errores"] = "; ".join(messages)
    return normalized


def validate_period_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    validated = [validate_period_row(row) for row in rows or []]
    _add_duplicate_warnings(validated)
    _add_overlap_warnings(validated)
    return validated


def has_critical_period_errors(rows: list[dict[str, Any]] | None) -> bool:
    return any(row.get("estado_validacion") == "ERROR" for row in validate_period_rows(rows))


def valid_period_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    return [row for row in validate_period_rows(rows) if row.get("estado_validacion") != "ERROR"]


def _add_duplicate_warnings(rows: list[dict[str, str]]) -> None:
    seen: dict[tuple[str, str, str, str, str], int] = {}
    duplicates: set[int] = set()
    for index, row in enumerate(rows):
        if row.get("estado_validacion") == "ERROR":
            continue
        key = (
            row["fecha_inicio"],
            row["fecha_fin"],
            row["ibl_reportado"],
            row["cargo"].lower(),
            row["entidad"].lower(),
        )
        previous = seen.get(key)
        if previous is not None:
            duplicates.update({previous, index})
        else:
            seen[key] = index

    for index in duplicates:
        _mark_warning(rows[index], "posible duplicado")


def _add_overlap_warnings(rows: list[dict[str, str]]) -> None:
    ranges: list[tuple[int, date, date]] = []
    for index, row in enumerate(rows):
        if row.get("estado_validacion") == "ERROR":
            continue
        ranges.append((index, date.fromisoformat(row["fecha_inicio"]), date.fromisoformat(row["fecha_fin"])))

    overlapped: set[int] = set()
    for pos, (left_index, left_start, left_end) in enumerate(ranges):
        for right_index, right_start, right_end in ranges[pos + 1 :]:
            if left_start <= right_end and right_start <= left_end:
                overlapped.update({left_index, right_index})

    for index in overlapped:
        _mark_warning(rows[index], "posible solapamiento")


def _mark_warning(row: dict[str, str], message: str) -> None:
    if message in row.get("errores", ""):
        return
    if row.get("estado_validacion") == "OK":
        row["estado_validacion"] = "ADVERTENCIA"
    _append_message(row, message)
