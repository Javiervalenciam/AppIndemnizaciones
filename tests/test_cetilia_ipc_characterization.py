from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from app_indemnizaciones.domain.exceptions import IpcImportError
from app_indemnizaciones.domain.models import PeriodoLaborado
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService

CURRENT_BEHAVIOR = "CURRENT_BEHAVIOR: characterization only; do not correct in this baseline."
KNOWN_BUG_FECHA_LIQUIDACION = (
    "KNOWN_BUG_FECHA_LIQUIDACION: requested date is ignored and latest IPC is used."
)


def _repo(values: list[tuple[str, object]]) -> IpcRepository:
    return IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": [row[0] for row in values],
                "Índice de Precios al Consumidor (IPC)": [row[1] for row in values],
            }
        )
    )


@pytest.mark.parametrize(
    ("raw_value", "observed"),
    [
        ("155.73", Decimal("155.73")),
        ("155,73", Decimal("15573")),
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
    ],
)
def test_current_behavior_ipc_text_number_formats(raw_value: str, observed: Decimal) -> None:
    repo = _repo([("2026-01-31", raw_value)])

    assert repo.get_current_ipc().indice == observed, CURRENT_BEHAVIOR


def test_current_behavior_ipc_empty_values_are_skipped_when_valid_rows_exist() -> None:
    repo = _repo(
        [
            ("2025-11-30", ""),
            ("2025-12-31", None),
            ("2026-01-31", "155.73"),
        ]
    )

    assert [(row.periodo, row.indice) for row in repo.registros] == [
        ("2026-01", Decimal("155.73"))
    ], CURRENT_BEHAVIOR


def test_current_behavior_ipc_only_empty_values_raise_import_error() -> None:
    with pytest.raises(IpcImportError, match="ningún registro IPC válido"):
        _repo([("2025-11-30", ""), ("2025-12-31", None)])


def test_current_behavior_ipc_duplicate_month_keeps_last_valid_row() -> None:
    repo = _repo([("2026-01-01", "155.73"), ("2026-01-31", "156.25")])

    assert len(repo.registros) == 1, CURRENT_BEHAVIOR
    assert repo.get_current_ipc().indice == Decimal("156.25"), CURRENT_BEHAVIOR


def test_current_behavior_ipc_missing_months_and_incomplete_year_are_allowed() -> None:
    repo = _repo([("1983-01-31", "10"), ("1983-03-31", "30")])

    info = repo.get_annual_average_ipc_info(1983)

    assert info.average == Decimal("20"), CURRENT_BEHAVIOR
    assert info.months_count == 2, CURRENT_BEHAVIOR
    assert info.missing_months == [2, 4, 5, 6, 7, 8, 9, 10, 11, 12], CURRENT_BEHAVIOR
    assert info.warnings == [
        "El año 1983 tiene 2 registros IPC; se usó promedio con meses disponibles."
    ], CURRENT_BEHAVIOR


def test_current_behavior_ipc_last_record_is_latest_period_not_input_order() -> None:
    repo = _repo(
        [
            ("2026-01-31", "155.73"),
            ("1983-01-31", "10"),
            ("2025-12-31", "154.20"),
        ]
    )

    current = repo.get_current_ipc()
    assert current.periodo == "2026-01", CURRENT_BEHAVIOR
    assert current.indice == Decimal("155.73"), CURRENT_BEHAVIOR


def test_current_behavior_ipc_future_record_becomes_current() -> None:
    repo = _repo([("2026-01-31", "155.73"), ("2030-01-31", "200")])

    current = repo.get_current_ipc()
    assert current.periodo == "2030-01", CURRENT_BEHAVIOR
    assert current.indice == Decimal("200"), CURRENT_BEHAVIOR


def test_known_bug_fecha_liquidacion_uses_latest_ipc_instead_of_requested_date() -> None:
    """KNOWN_BUG_FECHA_LIQUIDACION: freeze the defect without correcting it."""
    repo = _repo(
        [
            ("1983-01-31", "10"),
            ("2025-01-31", "100"),
            ("2026-01-31", "200"),
        ]
    )
    periodo = PeriodoLaborado(
        fecha_inicio=date(1983, 1, 1),
        fecha_fin=date(1983, 12, 31),
        ibl_reportado=Decimal("1000"),
        anio=1983,
    )

    result = LiquidacionService(repo).calcular(
        [periodo],
        fecha_liquidacion=date(2025, 1, 31),
    )

    assert result.periodos[0].periodo_ipc_actual == "2026-01", KNOWN_BUG_FECHA_LIQUIDACION
    assert result.periodos[0].ipc_actual == Decimal("200"), KNOWN_BUG_FECHA_LIQUIDACION
