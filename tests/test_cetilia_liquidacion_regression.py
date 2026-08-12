from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app_indemnizaciones.domain.models import PeriodoLaborado, ResultadoPeriodo
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService

BASELINE_PATH = Path(__file__).parent / "fixtures" / "regression" / "liquidacion_service_baseline.json"


def _load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


BASELINE = _load_baseline()


def _ipc_repository() -> IpcRepository:
    rows = BASELINE["ipc_historico"]
    return IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": [row["fecha"] for row in rows],
                "Índice de Precios al Consumidor (IPC)": [
                    Decimal(row["indice"]) for row in rows
                ],
            }
        )
    )


def _periodo(data: dict[str, Any]) -> PeriodoLaborado:
    return PeriodoLaborado(
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]),
        ibl_reportado=Decimal(data["ibl_reportado"]),
        anio=int(data["anio"]),
    )


def _assert_periodo_exact(actual: ResultadoPeriodo, expected: dict[str, Any]) -> None:
    assert actual.fecha_inicio == date.fromisoformat(expected["fecha_inicio"])
    assert actual.fecha_fin == date.fromisoformat(expected["fecha_fin"])
    assert actual.ibl_reportado == Decimal(expected["ibl_reportado"])
    assert actual.anio == expected["anio"]
    assert actual.dias == expected["dias"]
    assert actual.semanas == Decimal(expected["semanas"])
    assert actual.periodo_ipc_inicial == expected["periodo_ipc_inicial"]
    assert actual.ipc_inicial == Decimal(expected["ipc_inicial"])
    assert actual.periodo_ipc_actual == expected["periodo_ipc_actual"]
    assert actual.ipc_actual == Decimal(expected["ipc_actual"])
    assert actual.ibc_actualizado == Decimal(expected["ibc_actualizado"])
    assert actual.ibc_semanal_actualizado == Decimal(expected["ibc_semanal_actualizado"])


@pytest.mark.parametrize("case", BASELINE["cases"], ids=lambda case: case["id"])
def test_liquidacion_service_golden_current_behavior(case: dict[str, Any]) -> None:
    """Freeze current arithmetic exactly; these expectations are not legal validation."""
    result = LiquidacionService(_ipc_repository()).calcular(
        [_periodo(row) for row in case["periodos"]]
    )
    expected = case["expected"]

    assert len(result.periodos) == len(expected["periodos"])
    for actual_row, expected_row in zip(result.periodos, expected["periodos"], strict=True):
        _assert_periodo_exact(actual_row, expected_row)

    assert result.total_dias == expected["total_dias"]
    assert result.sc == Decimal(expected["sc"])
    assert result.sbc == Decimal(expected["sbc"])
    assert result.ppc == Decimal(expected["ppc"])
    assert result.isv == Decimal(expected["isv"])
