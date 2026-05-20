from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app_indemnizaciones.domain.models import PeriodoLaborado
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    CetilPeriodoCertificado,
    PeriodoLiquidableAnual,
)

PERIODO_COLUMNS = (
    "id",
    "anio",
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
        "anio": "",
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
        anio=int(normalized["anio"]) if normalized["anio"] else None,
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
            "anio": str(periodo.fecha_desde.year) if periodo.fecha_desde else "",
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
    annual_rows = result.filas_liquidables_anuales
    if not annual_rows:
        annual_rows, _warnings = normalize_cetil_to_annual_periods(result)
    return [periodo_liquidable_to_ui_row(row) for row in annual_rows]


def split_period_by_calendar_year(fecha_inicio: date, fecha_fin: date) -> list[dict[str, Any]]:
    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")

    segments: list[dict[str, Any]] = []
    current = fecha_inicio
    while current.year <= fecha_fin.year:
        end = min(date(current.year, 12, 31), fecha_fin)
        segments.append({"anio": current.year, "fecha_inicio": current, "fecha_fin": end})
        if end == fecha_fin:
            break
        current = date(current.year + 1, 1, 1)
    return segments


def normalize_cetil_to_annual_periods(
    result: CetilExtractionResult,
) -> tuple[list[PeriodoLiquidableAnual], list[str]]:
    warnings: list[str] = []
    periodos = sorted(
        [
            periodo
            for periodo in result.periodos_certificados
            if periodo.fecha_desde is not None and periodo.fecha_hasta is not None
        ],
        key=lambda row: row.fecha_desde or date.min,
    )
    segments = _segments_from_cetil_periods(periodos, warnings)
    consolidated = _consolidate_annual_segments(segments, warnings)
    ibl_by_year = _ibl_sugerido_by_year(result)

    rows: list[PeriodoLiquidableAnual] = []
    for segment in consolidated:
        anio = int(segment["anio"])
        ibl = ibl_by_year.get(anio)
        if ibl is None:
            warnings.append(f"No se detectó IBL para el año {anio}. Debe ingresarse manualmente.")
        rows.append(
            PeriodoLiquidableAnual(
                anio=anio,
                fecha_inicio=segment["fecha_inicio"],
                fecha_fin=segment["fecha_fin"],
                ibl_reportado=ibl,
                cargo=segment.get("cargo") or None,
                entidad=segment.get("entidad") or None,
                periodo_origen=segment.get("periodo_origen") or None,
            )
        )
    return rows, _dedupe(warnings)


def normalize_cetil_to_annual_rows(result: CetilExtractionResult) -> list[dict[str, str]]:
    rows, _warnings = normalize_cetil_to_annual_periods(result)
    return [periodo_liquidable_to_ui_row(row) for row in rows]


def periodo_liquidable_to_ui_row(periodo: PeriodoLiquidableAnual) -> dict[str, str]:
    row = new_period_row()
    row.update(
        {
            "anio": str(periodo.anio),
            "fecha_inicio": periodo.fecha_inicio.isoformat(),
            "fecha_fin": periodo.fecha_fin.isoformat(),
            "ibl_reportado": str(periodo.ibl_reportado) if periodo.ibl_reportado is not None else "",
            "cargo": periodo.cargo or "",
            "entidad": periodo.entidad or "",
            "fuente": periodo.fuente,
            "observaciones": periodo.observaciones,
        }
    )
    return normalize_period_row(row)


def _cetil_observaciones(periodo: CetilPeriodoCertificado) -> str:
    base = "Extraído de CETIL. Revisar IBL antes de calcular."
    if periodo.fuente_pagina:
        return f"{base} Página {periodo.fuente_pagina}."
    return base


def _segments_from_cetil_periods(
    periodos: list[CetilPeriodoCertificado],
    warnings: list[str],
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    previous_end: date | None = None

    for periodo in periodos:
        if periodo.fecha_desde is None or periodo.fecha_hasta is None:
            continue
        current_segments = split_period_by_calendar_year(periodo.fecha_desde, periodo.fecha_hasta)
        if (
            previous_end is not None
            and previous_end + timedelta(days=1) == periodo.fecha_desde
            and periodo.fecha_desde.year != periodo.fecha_hasta.year
            and periodo.fecha_hasta.month == 1
        ):
            for segment in current_segments:
                if segment["anio"] == periodo.fecha_desde.year:
                    segment["fecha_fin"] = periodo.fecha_desde
                    warnings.append(
                        "Se aplicó anualización tipo Excel base sobre un periodo contiguo que cruza año; "
                        f"revise manualmente el tramo posterior a {periodo.fecha_desde.isoformat()}."
                    )
                    break

        for segment in current_segments:
            segment["cargo"] = periodo.cargo or ""
            segment["entidad"] = periodo.entidad_responsable or ""
            segment["periodo_origen"] = (
                f"{periodo.fecha_desde.isoformat()}..{periodo.fecha_hasta.isoformat()}"
            )
            segments.append(segment)
        previous_end = periodo.fecha_hasta
    return segments


def _consolidate_annual_segments(
    segments: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    sorted_segments = sorted(segments, key=lambda row: (row["anio"], row["fecha_inicio"]))
    consolidated: list[dict[str, Any]] = []
    for segment in sorted_segments:
        if not consolidated or consolidated[-1]["anio"] != segment["anio"]:
            consolidated.append(segment.copy())
            continue

        current = consolidated[-1]
        if segment["fecha_inicio"] <= current["fecha_fin"] + timedelta(days=1):
            current["fecha_fin"] = max(current["fecha_fin"], segment["fecha_fin"])
            current["cargo"] = current.get("cargo") or segment.get("cargo", "")
            current["entidad"] = current.get("entidad") or segment.get("entidad", "")
            current["periodo_origen"] = _merge_origin(
                current.get("periodo_origen", ""),
                segment.get("periodo_origen", ""),
            )
        else:
            warnings.append(
                f"Se detectó brecha real en el año {segment['anio']}; se mantienen filas separadas."
            )
            consolidated.append(segment.copy())
    return consolidated


def _ibl_sugerido_by_year(result: CetilExtractionResult) -> dict[int, Decimal]:
    selected: dict[int, Decimal] = {}
    for factor in result.factores_salariales:
        if factor.ibl_sugerido is not None and factor.anio not in selected:
            selected[factor.anio] = factor.ibl_sugerido
    return selected


def _merge_origin(left: str, right: str) -> str:
    if not left:
        return right
    if not right or right in left:
        return left
    return f"{left}; {right}"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
