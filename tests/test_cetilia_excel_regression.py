from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

from app_indemnizaciones.domain.models import PeriodoLaborado, ResultadoLiquidacion
from app_indemnizaciones.services.excel_exporter import build_liquidacion_xlsx
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService


def _resultado() -> ResultadoLiquidacion:
    repo = IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": [
                    "1983-01-31",
                    "1983-02-28",
                    "1984-01-31",
                    "1984-02-29",
                    "2026-04-30",
                ],
                "Índice de Precios al Consumidor (IPC)": [
                    Decimal("10"),
                    Decimal("20"),
                    Decimal("40"),
                    Decimal("60"),
                    Decimal("200"),
                ],
            }
        )
    )
    return LiquidacionService(repo).calcular(
        [
            PeriodoLaborado(
                fecha_inicio=date(1983, 9, 29),
                fecha_fin=date(1983, 12, 31),
                ibl_reportado=Decimal("14000.123"),
                anio=1983,
            ),
            PeriodoLaborado(
                fecha_inicio=date(1984, 1, 1),
                fecha_fin=date(1984, 11, 30),
                ibl_reportado=Decimal("11298.987"),
                anio=1984,
            ),
        ]
    )


def _xlsx_sheets(resultado: ResultadoLiquidacion):
    content = build_liquidacion_xlsx(resultado)
    formulas = load_workbook(BytesIO(content), data_only=False)["Liquidación"]
    values = load_workbook(BytesIO(content), data_only=True)["Liquidación"]
    return formulas, values


def test_resultado_liquidacion_matches_xlsx_cached_values() -> None:
    resultado = _resultado()
    _formulas, values = _xlsx_sheets(resultado)

    for excel_row, period in zip((17, 18), resultado.periodos, strict=True):
        assert values[f"B{excel_row}"].value.date() == period.fecha_inicio
        assert values[f"C{excel_row}"].value.date() == period.fecha_fin
        assert values[f"D{excel_row}"].value == period.dias
        assert values[f"E{excel_row}"].value == pytest.approx(float(period.semanas))
        assert values[f"F{excel_row}"].value == pytest.approx(float(period.ibl_reportado))
        assert values[f"G{excel_row}"].value == pytest.approx(float(resultado.ppc))
        assert values[f"H{excel_row}"].value == pytest.approx(float(period.ipc_inicial))
        assert values[f"I{excel_row}"].value == pytest.approx(float(period.ipc_actual))
        assert values[f"J{excel_row}"].value == pytest.approx(
            float(period.ibc_actualizado)
        )
        assert values[f"K{excel_row}"].value == pytest.approx(
            float(period.ibc_semanal_actualizado)
        )

    assert values["D19"].value == resultado.total_dias
    assert values["E19"].value == pytest.approx(float(resultado.sc))
    assert values["K19"].value == pytest.approx(float(resultado.sbc))
    assert values["A13"].value == resultado.total_dias
    assert values["C13"].value == pytest.approx(float(resultado.sc))
    assert values["E13"].value == pytest.approx(float(resultado.sbc))
    assert values["I13"].value == pytest.approx(float(resultado.isv))


def test_excel_escribe_formulas_explicativas_con_valor_cacheado() -> None:
    resultado = _resultado()
    formulas, values = _xlsx_sheets(resultado)

    expected_formulas = {
        "D17": "=C17-B17+1",
        "E17": "=D17/7",
        "J17": "=F17*(I17/H17)",
        "K17": "=J17/$I$9",
        "D18": "=C18-B18+1",
        "K18": "=J18/$I$9",
        "D19": "=SUM(D17:D18)",
        "E19": "=D19/7",
        "K19": "=AVERAGE(K17:K18)",
        "A13": "=D19",
        "C13": "=E19",
        "E13": "=K19",
        "I13": "=E13*C13*G13",
    }
    for cell, formula in expected_formulas.items():
        assert formulas[cell].value == formula

    first = resultado.periodos[0]
    assert values["D17"].value == first.dias
    assert values["K17"].value == pytest.approx(
        float(first.ibc_semanal_actualizado)
    )
    assert values["I13"].value == pytest.approx(float(resultado.isv))


def test_excel_incluye_trazabilidad_por_fila() -> None:
    resultado = _resultado()
    content = build_liquidacion_xlsx(resultado)
    workbook = load_workbook(BytesIO(content), data_only=True)

    assert workbook.sheetnames == ["Liquidación", "Trazabilidad"]
    ws = workbook["Trazabilidad"]
    assert ws["A7"].value == 1983
    assert ws["D7"].value == resultado.periodos[0].dias
    assert ws["O7"].value == pytest.approx(
        float(resultado.periodos[0].ibc_actualizado)
    )
    assert ws["P7"].value == pytest.approx(
        float(resultado.periodos[0].ibc_semanal_actualizado)
    )
