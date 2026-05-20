from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app_indemnizaciones.domain.models import PeriodoLaborado
from app_indemnizaciones.services.cetil_models import CetilExtractionResult, CetilPeriodoCertificado

PERIODO_COLUMNS = (
    "id",
    "fecha_inicio",
    "fecha_fin",
    "ibl_reportado",
    "cargo",
    "entidad",
    "fuente",
    "observaciones",
    "estado_validacion",
    "errores",
)

FUENTES_PERMITIDAS = {"manual", "cetil", "importado"}

_THOUSANDS_COMMA_RE = re.compile(r"^[+-]?\d{1,3}(,\d{3})+$")
_THOUSANDS_DOT_RE = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+$")


def new_period_row() -> dict[str, str]:
    return {
        "id": uuid.uuid4().hex[:8],
        "fecha_inicio": "",
        "fecha_fin": "",
        "ibl_reportado": "",
        "cargo": "",
        "entidad": "",
        "fuente": "manual",
        "observaciones": "",
        "estado_validacion": "",
        "errores": "",
    }


def parse_ibl_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise ValueError("IBL reportado obligatorio")

    text = str(value).strip()
    if not text:
        raise ValueError("IBL reportado obligatorio")

    text = text.replace("$", "").replace(" ", "").replace("\u00a0", "")
    if not text:
        raise ValueError("IBL reportado obligatorio")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "") if _THOUSANDS_COMMA_RE.match(text) else text.replace(",", ".")
    elif "." in text and _THOUSANDS_DOT_RE.match(text):
        text = text.replace(".", "")

    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"IBL reportado no numérico: {value!r}") from exc

    if not number.is_finite():
        raise ValueError(f"IBL reportado no numérico: {value!r}")
    return number


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _decimal_to_store(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def normalize_period_row(row: dict[str, Any] | None) -> dict[str, str]:
    source = row or {}
    normalized = {column: _clean_text(source.get(column)) for column in PERIODO_COLUMNS}
    normalized["id"] = normalized["id"] or uuid.uuid4().hex[:8]
    normalized["fuente"] = (normalized["fuente"] or "manual").lower()

    ibl_text = normalized["ibl_reportado"]
    if ibl_text:
        try:
            normalized["ibl_reportado"] = _decimal_to_store(parse_ibl_decimal(ibl_text))
        except ValueError:
            normalized["ibl_reportado"] = ibl_text

    normalized["estado_validacion"] = ""
    normalized["errores"] = ""
    return normalized


def period_row_to_model(row: dict[str, Any]) -> PeriodoLaborado:
    normalized = normalize_period_row(row)
    return PeriodoLaborado(
        fecha_inicio=date.fromisoformat(normalized["fecha_inicio"]),
        fecha_fin=date.fromisoformat(normalized["fecha_fin"]),
        ibl_reportado=parse_ibl_decimal(normalized["ibl_reportado"]),
        cargo=normalized["cargo"] or None,
        entidad=normalized["entidad"] or None,
        fuente=normalized["fuente"] or None,
    )


def rows_to_periodos_laborados(rows: list[dict[str, Any]]) -> list[PeriodoLaborado]:
    return [period_row_to_model(row) for row in rows]


def cetil_period_to_ui_row(periodo: CetilPeriodoCertificado) -> dict[str, str]:
    row = new_period_row()
    row.update(
        {
            "fecha_inicio": periodo.fecha_desde.isoformat() if periodo.fecha_desde else "",
            "fecha_fin": periodo.fecha_hasta.isoformat() if periodo.fecha_hasta else "",
            "ibl_reportado": "",
            "cargo": periodo.cargo or "",
            "entidad": periodo.entidad_responsable or "",
            "fuente": "cetil",
            "observaciones": _cetil_observaciones(periodo),
        }
    )
    return normalize_period_row(row)


def cetil_extraction_to_period_rows(result: CetilExtractionResult) -> list[dict[str, str]]:
    return [cetil_period_to_ui_row(periodo) for periodo in result.periodos_certificados]


def _cetil_observaciones(periodo: CetilPeriodoCertificado) -> str:
    base = "Extraído de CETIL. Revisar IBL antes de calcular."
    if periodo.fuente_pagina:
        return f"{base} Página {periodo.fuente_pagina}."
    return base
