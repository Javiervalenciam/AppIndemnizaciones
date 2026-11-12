from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    CetilFactorSalarial,
    CetilPeriodoCertificado,
)
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService
from app_indemnizaciones.services.period_normalizer import (
    normalize_cetil_to_annual_periods,
    rows_to_periodos_laborados,
)
from app_indemnizaciones.utils.validators import validate_period_rows

CURRENT_BEHAVIOR = "CURRENT_BEHAVIOR: warnings do not block calculation."
FIXED_ANNUALIZATION = (
    "FIXED_ANNUALIZATION (D5): cross-year periods preserve every calendar day."
)


def _ui_row(
    row_id: str,
    fecha_inicio: str,
    fecha_fin: str,
    ibl: str = "14000",
) -> dict[str, str]:
    return {
        "id": row_id,
        "anio": fecha_inicio[:4],
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "ibl_reportado": ibl,
        "cargo": "Cargo",
        "entidad": "Entidad",
        "fuente": "manual",
        "observaciones": "",
    }


def _ipc_repo() -> IpcRepository:
    return IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": ["1983-01-31", "1984-01-31", "2026-01-31"],
                "Índice de Precios al Consumidor (IPC)": [
                    Decimal("10"),
                    Decimal("20"),
                    Decimal("100"),
                ],
            }
        )
    )


def _cetil_period(fecha_desde: date, fecha_hasta: date) -> CetilPeriodoCertificado:
    return CetilPeriodoCertificado(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        cargo="Cargo",
        entidad_responsable="Entidad",
    )


def _factor(anio: int, ibl: str) -> CetilFactorSalarial:
    value = Decimal(ibl)
    return CetilFactorSalarial(
        anio=anio,
        concepto="ASIGNACIÓN BÁSICA MENSUAL",
        valores_encontrados=[value] * 12,
        ibl_sugerido=value,
    )


def test_duplicate_periods_are_blocked_before_calculation() -> None:
    rows = validate_period_rows(
        [
            _ui_row("a", "1984-01-01", "1984-12-31"),
            _ui_row("b", "1984-01-01", "1984-12-31"),
        ]
    )

    # Un duplicado exacto también se solapa: duplicaría días y semanas.
    assert [row["estado_validacion"] for row in rows] == ["ERROR", "ERROR"]
    assert all("posible duplicado" in row["errores"] for row in rows)
    assert all("solapamiento" in row["errores"] for row in rows)


def test_overlapping_periods_are_blocked_before_calculation() -> None:
    rows = validate_period_rows(
        [
            _ui_row("a", "1984-01-01", "1984-06-30"),
            _ui_row("b", "1984-06-01", "1984-12-31", "15000"),
        ]
    )

    assert all(row["estado_validacion"] == "ERROR" for row in rows)
    assert all("solapamiento" in row["errores"] for row in rows)


def test_current_behavior_contiguous_cetil_periods_are_consolidated() -> None:
    rows, warnings = normalize_cetil_to_annual_periods(
        CetilExtractionResult(
            periodos_certificados=[
                _cetil_period(date(1984, 1, 1), date(1984, 6, 30)),
                _cetil_period(date(1984, 7, 1), date(1984, 12, 31)),
            ],
            factores_salariales=[_factor(1984, "11298")],
        )
    )

    assert len(rows) == 1, CURRENT_BEHAVIOR
    assert rows[0].fecha_inicio == date(1984, 1, 1), CURRENT_BEHAVIOR
    assert rows[0].fecha_fin == date(1984, 12, 31), CURRENT_BEHAVIOR
    assert not any("brecha real" in warning for warning in warnings), CURRENT_BEHAVIOR


def test_current_behavior_gap_keeps_multiple_rows_for_same_year() -> None:
    rows, warnings = normalize_cetil_to_annual_periods(
        CetilExtractionResult(
            periodos_certificados=[
                _cetil_period(date(1984, 1, 1), date(1984, 6, 30)),
                _cetil_period(date(1984, 7, 2), date(1984, 12, 31)),
            ],
            factores_salariales=[_factor(1984, "11298")],
        )
    )

    assert len(rows) == 2, CURRENT_BEHAVIOR
    assert [row.anio for row in rows] == [1984, 1984], CURRENT_BEHAVIOR
    assert [row.ibl_reportado for row in rows] == [
        Decimal("11298"),
        Decimal("11298"),
    ], CURRENT_BEHAVIOR
    assert any("brecha real" in warning for warning in warnings), CURRENT_BEHAVIOR


def test_cross_year_period_preserves_late_1987_dates() -> None:
    """D5: 1987-11-08..1987-12-31 must remain in the 1987 row (54 days)."""
    rows, warnings = normalize_cetil_to_annual_periods(
        CetilExtractionResult(
            periodos_certificados=[
                _cetil_period(date(1987, 1, 1), date(1987, 11, 6)),
                _cetil_period(date(1987, 11, 7), date(1988, 1, 17)),
            ],
            factores_salariales=[
                _factor(1987, "20510"),
                _factor(1988, "20510"),
            ],
        )
    )

    assert [(row.anio, row.fecha_inicio, row.fecha_fin) for row in rows] == [
        (1987, date(1987, 1, 1), date(1987, 12, 31)),
        (1988, date(1988, 1, 1), date(1988, 1, 17)),
    ], FIXED_ANNUALIZATION
    preserved_start = date(1987, 11, 8)
    preserved_end = date(1987, 12, 31)
    assert (preserved_end - preserved_start).days + 1 == 54, FIXED_ANNUALIZATION
    assert any(
        row.fecha_inicio <= preserved_start and preserved_end <= row.fecha_fin
        for row in rows
    ), FIXED_ANNUALIZATION
    assert not any("anualización tipo Excel base" in warning for warning in warnings), (
        FIXED_ANNUALIZATION
    )
