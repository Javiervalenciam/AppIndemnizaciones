from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from app_indemnizaciones.domain.models import PeriodoLaborado
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService


def test_liquidacion_single_period():
    repo = IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": ["1983/09/30", "2026/02/28"],
                "Índice de Precios al Consumidor (IPC)": [1.56, 155.73],
            }
        )
    )
    service = LiquidacionService(repo)
    result = service.calcular(
        [
            PeriodoLaborado(
                fecha_inicio=date(1983, 9, 29),
                fecha_fin=date(1984, 11, 30),
                ibl_reportado=Decimal("14000"),
            )
        ],
        fecha_liquidacion=date(2026, 2, 28),
    )

    row = result.periodos[0]
    assert row.dias == 421
    assert row.ipc_inicial == Decimal("1.56")
    assert row.ipc_actual == Decimal("155.73")
    assert row.ibc_actualizado.quantize(Decimal("0.01")) == Decimal("1397576.92")
    assert row.ibc_semanal_actualizado.quantize(Decimal("0.01")) == Decimal("321651.77")


def test_liquidacion_usa_ipc_promedio_anual_como_ipc_inicial():
    repo = IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": ["1983/01/31", "1983/02/28", "2026/02/28"],
                "Índice de Precios al Consumidor (IPC)": [10, 20, 100],
            }
        )
    )
    result = LiquidacionService(repo).calcular(
        [
            PeriodoLaborado(
                fecha_inicio=date(1983, 9, 29),
                fecha_fin=date(1983, 12, 31),
                ibl_reportado=Decimal("1000"),
                anio=1983,
            )
        ]
    )

    row = result.periodos[0]

    assert row.ipc_inicial == Decimal("15")
    assert row.ipc_inicial_origen == "PROMEDIO ANUAL 1983"
    assert row.periodo_ipc_inicial == "PROMEDIO ANUAL 1983"
    assert row.ipc_meses_usados == 2
    assert row.advertencias_ipc == (
        "El año 1983 tiene 2 registros IPC; se usó promedio con meses disponibles.",
    )
    assert row.ipc_actual == Decimal("100")
    assert row.ibc_actualizado.quantize(Decimal("0.01")) == Decimal("6666.67")
    assert row.ibc_semanal_actualizado.quantize(Decimal("0.01")) == Decimal("1534.33")


def test_liquidacion_calcula_sbc_sc_y_aportes_sin_redondeo_intermedio():
    repo = IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": ["1983/01/31", "1983/02/28", "1984/01/31", "1984/02/29", "2026/02/28"],
                "Índice de Precios al Consumidor (IPC)": [10, 20, 40, 60, 100],
            }
        )
    )
    result = LiquidacionService(repo).calcular(
        [
            PeriodoLaborado(date(1983, 1, 1), date(1983, 12, 31), Decimal("1000"), anio=1983),
            PeriodoLaborado(date(1984, 1, 1), date(1984, 12, 31), Decimal("2000"), anio=1984),
        ]
    )

    weekly_1983 = (Decimal("1000") * (Decimal("100") / Decimal("15"))) / Decimal("4.345")
    weekly_1984 = (Decimal("2000") * (Decimal("100") / Decimal("50"))) / Decimal("4.345")

    assert result.total_dias == 720
    assert result.sc == Decimal(720) / Decimal(7)
    assert result.sbc == (weekly_1983 + weekly_1984) / Decimal(2)
    assert result.ppc == Decimal("0.0227")
    assert result.isv == result.sbc * result.sc * result.ppc
