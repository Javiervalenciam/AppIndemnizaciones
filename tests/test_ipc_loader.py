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


def test_get_annual_average_ipc_calcula_promedio_anual():
    df = pd.DataFrame(
        {
            "Fecha": ["1983/01/31", "1983/02/28", "1983/03/31"],
            "Índice de Precios al Consumidor (IPC)": [Decimal("10"), Decimal("20"), Decimal("30")],
        }
    )
    repo = IpcRepository.from_dataframe(df)

    info = repo.get_annual_average_ipc_info(1983)

    assert info.average == Decimal("20")
    assert repo.get_annual_average_ipc(1983) == Decimal("20")
    assert info.months_count == 3


def test_get_annual_average_ipc_meses_incompletos_advierte():
    df = pd.DataFrame(
        {
            "Fecha": ["1983/01/31", "1983/03/31"],
            "Índice de Precios al Consumidor (IPC)": [Decimal("10"), Decimal("30")],
        }
    )
    repo = IpcRepository.from_dataframe(df)

    info = repo.get_annual_average_ipc_info(1983)

    assert info.average == Decimal("20")
    assert info.months_count == 2
    assert info.missing_months == [2, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    assert info.warnings == [
        "El año 1983 tiene 2 registros IPC; se usó promedio con meses disponibles."
    ]


def test_get_annual_average_ipc_falla_si_no_hay_anio():
    df = pd.DataFrame(
        {
            "Fecha": ["2026/02/28"],
            "Índice de Precios al Consumidor (IPC)": [155.73],
        }
    )
    repo = IpcRepository.from_dataframe(df)

    with pytest.raises(IpcNotFoundError):
        repo.get_annual_average_ipc(1983)


def test_get_current_ipc_devuelve_ultimo_registro_valido():
    df = pd.DataFrame(
        {
            "Fecha": ["1983/09/30", "2026/02/28"],
            "Índice de Precios al Consumidor (IPC)": [1.56, 155.73],
        }
    )
    repo = IpcRepository.from_dataframe(df)

    current = repo.get_current_ipc()

    assert current.periodo == "2026-02"
    assert current.indice == Decimal("155.73")
