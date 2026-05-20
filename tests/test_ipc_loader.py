from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app_indemnizaciones.domain.exceptions import IpcNotFoundError
from app_indemnizaciones.services.ipc_loader import IpcRepository


def test_ipc_loader_banco_republica_schema():
    df = pd.DataFrame(
        {
            "Fecha": ["yyyy/mm/dd", "1983/09/30", "1983/10/31", "2026/02/28"],
            "Índice de Precios al Consumidor (IPC)": ["índice", 1.56, 1.62, 155.73],
        }
    )
    repo = IpcRepository.from_dataframe(df)

    summary = repo.summary()
    assert summary.total_registros == 3
    assert summary.periodo_minimo == "1983-09"
    assert summary.periodo_maximo == "2026-02"
    assert summary.ipc_actual == Decimal("155.73")

    pair = repo.obtener_ipc("1983-09-01")
    assert pair.ipc_inicial == Decimal("1.56")
    assert pair.ipc_actual == Decimal("155.73")


def test_ipc_loader_legacy_schema():
    df = pd.DataFrame(
        {
            "Año(aaaa)-Mes(mm)": [198309, 198310, 202602],
            "Índice": [1.56, 1.62, 155.73],
        }
    )
    repo = IpcRepository.from_dataframe(df)

    pair = repo.obtener_ipc("1983-09-29", "2026-02-28")
    assert pair.periodo_inicial == "1983-09"
    assert pair.periodo_actual == "2026-02"


def test_ipc_not_found_error():
    df = pd.DataFrame(
        {
            "Fecha": ["2026/02/28"],
            "Índice de Precios al Consumidor (IPC)": [155.73],
        }
    )
    repo = IpcRepository.from_dataframe(df)

    with pytest.raises(IpcNotFoundError):
        repo.obtener_ipc("1983-09-29")
