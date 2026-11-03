from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

from app_indemnizaciones.domain.models import PeriodoLaborado, ResultadoLiquidacion
from app_indemnizaciones.services.cetil_models import (
    CetilEntidadEmpleadora,
    CetilExtractionResult,
    CetilMetadata,
    CetilTrabajador,
)
from app_indemnizaciones.services.excel_exporter import (
    TABLE_HEADERS,
    TITLE,
    build_ipc_export_info,
    build_liquidacion_filename,
    build_liquidacion_xlsx,
    safe_filename_document,
)
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService


def _repo() -> IpcRepository:
    return IpcRepository.from_dataframe(
        pd.DataFrame(
            {
                "Fecha": ["1983/01/31", "1983/02/28", "2026/02/28"],
                "Índice de Precios al Consumidor (IPC)": [10, 20, 100],
            }
        )
    )


def _resultado() -> tuple[ResultadoLiquidacion, IpcRepository]:
    repo = _repo()
    resultado = LiquidacionService(repo).calcular(
        [
            PeriodoLaborado(
                date(1983, 9, 29),
                date(1983, 12, 31),
                Decimal("14000"),
                anio=1983,
            )
        ]
    )
    return resultado, repo


def test_exportador_incluye_columnas_kpis_datos_cetil_e_ipc():
    resultado, repo = _resultado()
    xlsx = build_liquidacion_xlsx(
        resultado,
        cetil_result=_cetil_result(),
        ipc_info=build_ipc_export_info(repo),
    )

    ws = load_workbook(BytesIO(xlsx), data_only=True)["Liquidación"]

    assert ws["A1"].value == TITLE
    assert ws["A5"].value == "Nombre completo"
    assert ws["C5"].value == "Persona Prueba"
    assert ws["G5"].value == "Número CETIL"
    assert ws["I5"].value == "123456789"
    assert ws["G8"].value == "IPC actual/final"
    assert ws["I8"].value == 100
    assert ws["G9"].value == "Divisor semanal"
    assert ws["I9"].value == pytest.approx(4.345)

    headers = [ws.cell(row=16, column=column).value for column in range(1, 12)]
    assert headers == list(TABLE_HEADERS)

    assert ws["A18"].value == "TOTALES DEL PERÍODO"
    assert ws["D18"].value == resultado.total_dias
    assert ws["J18"].value == "SBC"
    assert ws["K18"].value == pytest.approx(float(resultado.sbc))
    assert ws["A20"].value.startswith("Advertencias:")
    assert "El año 1983 tiene 2 registros IPC" in ws["A20"].value


def test_exportador_escribe_formulas_con_valor_cacheado_del_backend():
    resultado, repo = _resultado()
    xlsx = build_liquidacion_xlsx(
        resultado,
        cetil_result=_cetil_result(),
        ipc_info=build_ipc_export_info(repo, fecha_liquidacion=resultado.fecha_liquidacion),
    )

    formulas = load_workbook(BytesIO(xlsx), data_only=False)["Liquidación"]
    values = load_workbook(BytesIO(xlsx), data_only=True)["Liquidación"]
    row = resultado.periodos[0]

    expected_formulas = {
        "D17": "=C17-B17+1",
        "E17": "=D17/7",
        "G17": "=$G$13",
        "J17": "=F17*(I17/H17)",
        "K17": "=J17/$I$9",
        "D18": "=SUM(D17:D17)",
        "E18": "=D18/7",
        "K18": "=AVERAGE(K17:K17)",
        "A13": "=D18",
        "C13": "=E18",
        "E13": "=K18",
        "I13": "=E13*C13*G13",
    }
    for cell, formula in expected_formulas.items():
        assert formulas[cell].value == formula

    # El PPC es un parámetro del libro, no una fórmula calculada.
    assert formulas["G13"].value == pytest.approx(float(resultado.ppc))

    assert values["D17"].value == row.dias == 94
    assert values["E17"].value == pytest.approx(float(row.semanas))
    assert values["J17"].value == pytest.approx(float(row.ibc_actualizado))
    assert values["K17"].value == pytest.approx(float(row.ibc_semanal_actualizado))
    assert values["D18"].value == resultado.total_dias
    assert values["E18"].value == pytest.approx(float(resultado.sc))
    assert values["K18"].value == pytest.approx(float(resultado.sbc))
    assert values["A13"].value == resultado.total_dias
    assert values["C13"].value == pytest.approx(float(resultado.sc))
    assert values["E13"].value == pytest.approx(float(resultado.sbc))
    assert values["I13"].value == pytest.approx(float(resultado.isv))


def test_exportador_configura_impresion_del_reporte_en_una_hoja():
    resultado, repo = _resultado()
    xlsx = build_liquidacion_xlsx(
        resultado,
        cetil_result=_cetil_result(),
        ipc_info=build_ipc_export_info(repo),
    )

    ws = load_workbook(BytesIO(xlsx))["Liquidación"]

    assert ws.page_setup.orientation == "landscape"
    assert ws.sheet_properties.pageSetUpPr.fitToPage is True
    # xlsxwriter omite fitToWidth/fitToHeight cuando valen 1 (valor por defecto).
    assert ws.page_setup.fitToWidth in (None, 1)
    assert ws.page_setup.fitToHeight in (None, 1)
    assert "$A$1:$K$20" in str(ws.print_area)
    assert ws.sheet_view.showGridLines is False
    assert ws.page_margins.left == pytest.approx(0.25)
    assert ws.page_margins.right == pytest.approx(0.25)
    assert ws.page_margins.top == pytest.approx(0.35)
    assert ws.page_margins.bottom == pytest.approx(0.45)


def test_exportador_incluye_hoja_de_trazabilidad():
    resultado, _ = _resultado()
    xlsx = build_liquidacion_xlsx(resultado, cetil_result=_cetil_result())

    workbook = load_workbook(BytesIO(xlsx), data_only=True)
    assert workbook.sheetnames == ["Liquidación", "Trazabilidad"]
    ws = workbook["Trazabilidad"]

    assert ws["A1"].value == "TRAZABILIDAD DE LA LIQUIDACIÓN"
    assert ws["A3"].value == "Fecha de liquidación"
    assert ws["A4"].value == "Convención de días"
    headers = [ws.cell(row=6, column=column).value for column in range(1, 23)]
    assert headers[:5] == ["Año", "Fecha inicio", "Fecha fin", "Días calendario", "Semanas"]
    assert headers[-1] == "Documento CETIL"
    assert ws["A7"].value == 1983
    assert ws["D7"].value == 94
    assert ws["J7"].value == 15
    assert ws["O7"].value == pytest.approx(float(resultado.periodos[0].ibc_actualizado))
    assert ws["P7"].value == pytest.approx(
        float(resultado.periodos[0].ibc_semanal_actualizado)
    )


def test_trazabilidad_usa_formulas_y_se_imprime_a_dos_paginas_de_ancho():
    resultado, _ = _resultado()
    xlsx = build_liquidacion_xlsx(resultado, cetil_result=_cetil_result())

    formulas = load_workbook(BytesIO(xlsx), data_only=False)["Trazabilidad"]
    assert formulas["D7"].value == "=C7-B7+1"
    assert formulas["E7"].value == "=D7/7"
    assert formulas["N7"].value == "=M7/J7"
    assert formulas["O7"].value == "=F7*N7"
    assert formulas["P7"].value == "=O7/$P$4"

    ws = load_workbook(BytesIO(xlsx))["Trazabilidad"]
    assert ws.sheet_properties.pageSetUpPr.fitToPage is True
    assert ws.page_setup.fitToWidth == 2
    assert ws.page_setup.fitToHeight == 0
    assert ws.sheet_view.showGridLines is False


def test_exportador_trazabilidad_conserva_el_documento_cetil_de_la_fila():
    repo = _repo()
    resultado = LiquidacionService(repo).calcular(
        [
            PeriodoLaborado(
                date(1983, 9, 29),
                date(1983, 12, 31),
                Decimal("14000"),
                anio=1983,
                documento_cetil="CETIL A-1 · 2024-01-10",
            )
        ]
    )

    workbook = load_workbook(
        BytesIO(build_liquidacion_xlsx(resultado)),
        data_only=True,
    )
    ws = workbook["Trazabilidad"]

    assert ws["V6"].value == "Documento CETIL"
    assert ws["V7"].value == "CETIL A-1 · 2024-01-10"


def test_nombre_archivo_incluye_documento():
    assert build_liquidacion_filename(_cetil_result()) == "Liquidacion_ISV_100.xlsx"
    assert safe_filename_document("88,152,324") == "88152324"


def test_nombre_archivo_sin_documento():
    assert build_liquidacion_filename() == "Liquidacion_ISV_sin_documento.xlsx"
    assert safe_filename_document(None) == "sin_documento"
    assert safe_filename_document("---") == "sin_documento"


def _cetil_result() -> CetilExtractionResult:
    return CetilExtractionResult(
        metadata=CetilMetadata(
            numero_cetil="123456789",
            ciudad_expedicion="BOGOTA",
            fecha_expedicion_cetil=date(2020, 1, 2),
        ),
        trabajador=CetilTrabajador(
            tipo_documento="CC",
            documento="100",
            nombre_completo="Persona Prueba",
            fecha_nacimiento=date(1960, 1, 1),
        ),
        entidad_empleadora=CetilEntidadEmpleadora(
            nombre_entidad_empleadora="Entidad Prueba",
            nit_entidad_empleadora="800100200",
        ),
    )
