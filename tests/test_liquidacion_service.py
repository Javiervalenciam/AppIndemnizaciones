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
