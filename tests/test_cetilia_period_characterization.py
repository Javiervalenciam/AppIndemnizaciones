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
LEGACY_CURRENT_BEHAVIOR = (
    "LEGACY_CURRENT_BEHAVIOR: freeze annualization output even when dates disappear."
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


def test_current_behavior_duplicate_periods_warn_but_both_are_calculated() -> None:
    rows = validate_period_rows(
        [
            _ui_row("a", "1984-01-01", "1984-12-31"),
            _ui_row("b", "1984-01-01", "1984-12-31"),
        ]
    )

    assert [row["estado_validacion"] for row in rows] == [
        "ADVERTENCIA",
        "ADVERTENCIA",
    ], CURRENT_BEHAVIOR
    assert all("posible duplicado" in row["errores"] for row in rows), CURRENT_BEHAVIOR

    result = LiquidacionService(_ipc_repo()).calcular(rows_to_periodos_laborados(rows))
    assert len(result.periodos) == 2, CURRENT_BEHAVIOR
    assert result.total_dias == 720, CURRENT_BEHAVIOR
    assert result.sc == Decimal(720) / Decimal(7), CURRENT_BEHAVIOR


def test_current_behavior_overlapping_periods_warn_but_days_are_summed() -> None:
    rows = validate_period_rows(
        [
            _ui_row("a", "1984-01-01", "1984-06-30"),
            _ui_row("b", "1984-06-01", "1984-12-31", "15000"),
        ]
    )

    assert all(row["estado_validacion"] == "ADVERTENCIA" for row in rows), CURRENT_BEHAVIOR
    assert all("posible solapamiento" in row["errores"] for row in rows), CURRENT_BEHAVIOR

    result = LiquidacionService(_ipc_repo()).calcular(rows_to_periodos_laborados(rows))
    assert [row.dias for row in result.periodos] == [179, 210], CURRENT_BEHAVIOR
    assert result.total_dias == 389, CURRENT_BEHAVIOR


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


def test_legacy_current_behavior_cross_year_period_loses_late_1987_dates() -> None:
    """LEGACY_CURRENT_BEHAVIOR: 1987-11-08..1987-12-31 disappears (54 days)."""
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
        (1987, date(1987, 1, 1), date(1987, 11, 7)),
        (1988, date(1988, 1, 1), date(1988, 1, 17)),
    ], LEGACY_CURRENT_BEHAVIOR
    disappeared_start = date(1987, 11, 8)
    disappeared_end = date(1987, 12, 31)
    assert (disappeared_end - disappeared_start).days + 1 == 54, LEGACY_CURRENT_BEHAVIOR
    assert all(
        not (row.fecha_inicio <= disappeared_start <= row.fecha_fin) for row in rows
    ), LEGACY_CURRENT_BEHAVIOR
    assert any("anualización tipo Excel base" in warning for warning in warnings), (
        LEGACY_CURRENT_BEHAVIOR
    )
