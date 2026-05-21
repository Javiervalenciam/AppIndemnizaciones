from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from app_indemnizaciones.domain.models import PeriodoLaborado
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    CetilFactorSalarial,
    CetilPeriodoCertificado,
)
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService
from app_indemnizaciones.services.period_normalizer import normalize_cetil_to_annual_periods


def test_regresion_excel_base_anualizacion_ibl_y_liquidacion():
    rows, _warnings = normalize_cetil_to_annual_periods(
        CetilExtractionResult(
            periodos_certificados=[
                _periodo(date(1983, 9, 29), date(1984, 11, 30)),
                _periodo(date(1984, 12, 1), date(1987, 11, 6)),
                _periodo(date(1987, 11, 7), date(1988, 1, 17)),
            ],
            factores_salariales=[
                _factor(1983, Decimal("14000")),
                _factor(1984, Decimal("11298")),
                _factor(1985, Decimal("16500")),
                _factor(1986, Decimal("16850")),
                _factor(1987, Decimal("20510")),
                _factor(1988, Decimal("20510")),
            ],
        )
    )

    assert [(row.anio, row.fecha_inicio, row.fecha_fin, row.ibl_reportado) for row in rows] == [
        (1983, date(1983, 9, 29), date(1983, 12, 31), Decimal("14000")),
        (1984, date(1984, 1, 1), date(1984, 12, 31), Decimal("11298")),
        (1985, date(1985, 1, 1), date(1985, 12, 31), Decimal("16500")),
        (1986, date(1986, 1, 1), date(1986, 12, 31), Decimal("16850")),
        (1987, date(1987, 1, 1), date(1987, 11, 7), Decimal("20510")),
        (1988, date(1988, 1, 1), date(1988, 1, 17), Decimal("20510")),
    ]

    repo = IpcRepository.from_dataframe(_ipc_fixture())
    result = LiquidacionService(repo).calcular(
        [
            PeriodoLaborado(
                fecha_inicio=row.fecha_inicio,
                fecha_fin=row.fecha_fin,
                ibl_reportado=row.ibl_reportado or Decimal(0),
                anio=row.anio,
            )
            for row in rows
        ]
    )

    assert [row.dias for row in result.periodos] == [92, 360, 360, 360, 306, 16]
    assert [row.semanas.quantize(Decimal("0.01")) for row in result.periodos] == [
        Decimal("13.14"),
        Decimal("51.43"),
        Decimal("51.43"),
        Decimal("51.43"),
        Decimal("43.71"),
        Decimal("2.29"),
    ]

    first = result.periodos[0]
    assert first.ibc_actualizado == Decimal("14000") * (Decimal("100") / Decimal("10"))
    assert first.ibc_semanal_actualizado == first.ibc_actualizado / Decimal("4.345")
    assert result.isv == result.sbc * result.sc * result.ppc


def _periodo(fecha_desde: date, fecha_hasta: date) -> CetilPeriodoCertificado:
    return CetilPeriodoCertificado(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        cargo="Cargo",
        entidad_responsable="Entidad",
    )


def _factor(anio: int, value: Decimal) -> CetilFactorSalarial:
    return CetilFactorSalarial(
        anio=anio,
        concepto="ASIGNACIÓN BÁSICA MENSUAL",
        valores_mensuales={},
        valores_encontrados=[value] * 12,
        asignacion_basica_mensual=value,
        ibl_sugerido=value,
    )


def _ipc_fixture() -> pd.DataFrame:
    rows = [
        {
            "Fecha": f"{year}/{month:02d}/28",
            "Índice de Precios al Consumidor (IPC)": value,
        }
        for year, value in {
            1983: 10,
            1984: 20,
            1985: 25,
            1986: 40,
            1987: 50,
            1988: 80,
        }.items()
        for month in range(1, 13)
    ]
    rows.append({"Fecha": "2026/02/28", "Índice de Precios al Consumidor (IPC)": 100})
    return pd.DataFrame(rows)
