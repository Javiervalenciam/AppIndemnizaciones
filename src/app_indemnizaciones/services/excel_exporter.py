from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app_indemnizaciones.domain.models import ResultadoLiquidacion, ResultadoPeriodo
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    PeriodoLiquidableAnual,
)
from app_indemnizaciones.services.ipc_loader import IpcRepository


@dataclass(frozen=True)
class IpcExportInfo:
    ipc_actual: Decimal
    fecha_ipc_actual: date
    total_registros: int
    periodo: str = ""


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def safe_filename_document(documento: str | None) -> str:
    if not documento:
        return "sin_documento"
    safe = re.sub(r"\W+", "", str(documento), flags=re.ASCII)
    return safe or "sin_documento"


def build_liquidacion_filename(cetil_result: CetilExtractionResult | None = None) -> str:
    trabajador = cetil_result.trabajador if cetil_result else None
    return f"Liquidacion_ISV_{safe_filename_document(trabajador.documento if trabajador else None)}.xlsx"


def build_ipc_export_info(
    repo: IpcRepository,
    fecha_liquidacion: date | None = None,
) -> IpcExportInfo:
    """Resume el IPC para el libro exportado.

    Si se indica fecha de liquidación, se usa el registro IPC de ese periodo;
    de lo contrario, el último registro disponible (mismo criterio del motor).
    """
    current = (
        repo.obtener_por_fecha(fecha_liquidacion)
        if fecha_liquidacion is not None
        else repo.get_current_ipc()
    )
    return IpcExportInfo(
        ipc_actual=current.indice,
        fecha_ipc_actual=current.fecha,
        total_registros=len(repo.registros),
        periodo=current.periodo,
    )


def build_liquidacion_xlsx(
    resultado: ResultadoLiquidacion,
    *,
    cetil_result: CetilExtractionResult | None = None,
    ipc_info: IpcExportInfo | None = None,
) -> bytes:
    """Genera el XLSX con los valores ya calculados por el backend.

    El libro no contiene fórmulas de cálculo: días, indexación e ISV se
    escriben como valores para que Excel no pueda producir un segundo
    resultado distinto al del motor.
    """
    output = io.BytesIO()

    with _ExcelWorkbook(output) as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet("Liquidación")
        traceability = workbook.add_worksheet("Trazabilidad")
        formats = _build_formats(workbook)

        _write_liquidacion_sheet(
            worksheet,
            resultado,
            cetil_result=cetil_result,
            ipc_info=ipc_info,
            formats=formats,
        )
        _write_traceability_sheet(
            traceability,
            resultado,
            cetil_result=cetil_result,
            ipc_info=ipc_info,
            formats=formats,
        )

    return output.getvalue()


class _ExcelWorkbook:
    """Contexto mínimo para escribir varias hojas con xlsxwriter."""

    def __init__(self, output: io.BytesIO) -> None:
        import xlsxwriter

        self.output = output
        self.book = xlsxwriter.Workbook(output, {"in_memory": True})

    def __enter__(self) -> _ExcelWorkbook:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.book.close()


def _build_formats(workbook) -> dict[str, object]:  # noqa: ANN001
    return {
        "title": workbook.add_format(
            {"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"}
        ),
        "header": workbook.add_format(
            {
                "bold": True,
                "bg_color": "#D9EAF7",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        ),
        "money": workbook.add_format({"num_format": "$ #,##0.00", "border": 1}),
        "num": workbook.add_format({"num_format": "#,##0.000", "border": 1}),
        "percent": workbook.add_format({"num_format": "0.000%", "border": 1}),
        "int": workbook.add_format({"num_format": "#,##0", "border": 1}),
        "date": workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1}),
        "cell": workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"}),
        "label": workbook.add_format(
            {"bold": True, "bg_color": "#F3F6FA", "border": 1, "valign": "top"}
        ),
        "total_label": workbook.add_format(
            {"bold": True, "bg_color": "#E2F0D9", "border": 1}
        ),
        "total_value": workbook.add_format(
            {"bold": True, "num_format": "$ #,##0.00", "border": 1}
        ),
        "note": workbook.add_format({"italic": True, "font_color": "#5B6475"}),
    }


def _write_liquidacion_sheet(
    worksheet,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    *,
    cetil_result: CetilExtractionResult | None,
    ipc_info: IpcExportInfo | None,
    formats: dict[str, object],
) -> None:
    worksheet.merge_range(
        "A1:K1",
        "LIQUIDACIÓN DE INDEMNIZACIÓN SUSTITUTIVA DE VEJEZ",
        formats["title"],
    )
    _write_cetil_metadata(
        worksheet,
        cetil_result,
        formats["label"],
        formats["cell"],
        formats["date"],
    )
    _write_ipc_metadata(
        worksheet,
        ipc_info,
        resultado,
        formats["label"],
        formats["cell"],
        formats["date"],
        formats["num"],
    )

    headers = [
        "AÑO",
        "FECHA DESDE",
        "FECHA HASTA",
        "No. Días",
        "No. Sem.",
        "IBL Reportado",
        "% Apl.",
        "IPC Inicial",
        "IPC Actual",
        "Indexación IBC Mensual",
        "IBC Semanal Actualizado",
    ]
    for col_num, value in enumerate(headers):
        worksheet.write(12, col_num, value, formats["header"])

    widths = [8, 14, 14, 12, 12, 16, 10, 12, 12, 22, 24]
    for col_num, width in enumerate(widths):
        worksheet.set_column(col_num, col_num, width)

    first_data_row = 13
    for offset, row in enumerate(resultado.periodos):
        excel_row = first_data_row + offset
        worksheet.set_row(excel_row, 20)
        worksheet.write(excel_row, 0, row.anio or row.fecha_inicio.year, formats["cell"])
        worksheet.write_datetime(excel_row, 1, row.fecha_inicio, formats["date"])
        worksheet.write_datetime(excel_row, 2, row.fecha_fin, formats["date"])
        worksheet.write_number(excel_row, 3, row.dias, formats["int"])
        worksheet.write_number(excel_row, 4, float(row.semanas), formats["num"])
        worksheet.write_number(excel_row, 5, _money(row.ibl_reportado), formats["money"])
        worksheet.write_number(excel_row, 6, float(resultado.ppc), formats["percent"])
        worksheet.write_number(excel_row, 7, float(row.ipc_inicial), formats["num"])
        worksheet.write_number(excel_row, 8, float(row.ipc_actual), formats["num"])
        worksheet.write_number(excel_row, 9, _money(row.ibc_actualizado), formats["money"])
        worksheet.write_number(
            excel_row, 10, _money(row.ibc_semanal_actualizado), formats["money"]
        )

    last_data_row = first_data_row + len(resultado.periodos) - 1
    total_row = last_data_row + 3
    worksheet.write(total_row, 0, "DÍAS EN TOTAL", formats["total_label"])
    worksheet.write_number(total_row, 1, resultado.total_dias, formats["int"])
    worksheet.write(total_row + 1, 0, "SC", formats["total_label"])
    worksheet.write_number(total_row + 1, 1, float(resultado.sc), formats["num"])
    worksheet.write(total_row + 2, 0, "PPC", formats["total_label"])
    worksheet.write_number(total_row + 2, 1, float(resultado.ppc), formats["percent"])
    worksheet.write(total_row + 3, 0, "SBC", formats["total_label"])
    worksheet.write_number(total_row + 3, 1, _money(resultado.sbc), formats["total_value"])
    worksheet.write(total_row + 4, 0, "LIQUIDACIÓN DE APORTES", formats["total_label"])
    worksheet.write_number(total_row + 4, 1, _money(resultado.isv), formats["total_value"])
    worksheet.write(total_row + 5, 0, "SBC x SC x PPC", formats["total_label"])
    worksheet.write(
        total_row + 6,
        0,
        "Valores calculados por el motor. El libro no contiene fórmulas de cálculo.",
        formats["note"],
    )

    worksheet.freeze_panes(13, 0)


def _write_cetil_metadata(
    worksheet,  # noqa: ANN001
    result: CetilExtractionResult | None,
    label_fmt,
    cell_fmt,
    date_fmt,
) -> None:
    metadata = result.metadata if result else None
    trabajador = result.trabajador if result else None
    entidad = result.entidad_empleadora if result else None
    values = [
        ("Nombre completo", trabajador.nombre_completo if trabajador else None),
        ("Documento", trabajador.documento if trabajador else None),
        ("Fecha nacimiento", trabajador.fecha_nacimiento if trabajador else None),
        ("Número CETIL", metadata.numero_cetil if metadata else None),
        ("Fecha CETIL", metadata.fecha_expedicion_cetil if metadata else None),
        ("Entidad empleadora", entidad.nombre_entidad_empleadora if entidad else None),
        ("NIT entidad", entidad.nit_entidad_empleadora if entidad else None),
    ]
    for index, (label, value) in enumerate(values, start=1):
        worksheet.write(index, 0, label, label_fmt)
        if isinstance(value, date):
            worksheet.write_datetime(index, 1, value, date_fmt)
        else:
            worksheet.write(index, 1, value or "No detectado", cell_fmt)


def _write_ipc_metadata(
    worksheet,  # noqa: ANN001
    ipc_info: IpcExportInfo | None,
    resultado: ResultadoLiquidacion,
    label_fmt,
    cell_fmt,
    date_fmt,
    num_fmt,
) -> None:
    worksheet.write(1, 3, "IPC actual/final", label_fmt)
    if ipc_info:
        worksheet.write_number(1, 4, float(ipc_info.ipc_actual), num_fmt)
        worksheet.write(2, 3, "Fecha IPC actual/final", label_fmt)
        worksheet.write_datetime(2, 4, ipc_info.fecha_ipc_actual, date_fmt)
        worksheet.write(3, 3, "Registros IPC", label_fmt)
        worksheet.write_number(3, 4, ipc_info.total_registros, cell_fmt)
    else:
        worksheet.write(1, 4, "No disponible", cell_fmt)

    warnings = _ipc_warnings(resultado)
    worksheet.write(4, 3, "Advertencias IPC anual", label_fmt)
    worksheet.write(4, 4, "\n".join(warnings) if warnings else "Sin advertencias", cell_fmt)

    worksheet.write(5, 3, "Fecha de liquidación", label_fmt)
    if resultado.fecha_liquidacion:
        worksheet.write_datetime(5, 4, resultado.fecha_liquidacion, date_fmt)
    else:
        worksheet.write(5, 4, "No indicada", cell_fmt)

    worksheet.write(6, 3, "Fuente IPC actual", label_fmt)
    worksheet.write(6, 4, resultado.ipc_actual_fuente or "N/D", cell_fmt)

    worksheet.write(7, 3, "Período IPC actual", label_fmt)
    worksheet.write(7, 4, resultado.ipc_actual_periodo or "N/D", cell_fmt)

    worksheet.write(8, 3, "Convención de días", label_fmt)
    worksheet.write(8, 4, "Días calendario reales (incluye extremos)", cell_fmt)


def _write_traceability_sheet(
    worksheet,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    *,
    cetil_result: CetilExtractionResult | None,
    ipc_info: IpcExportInfo | None,
    formats: dict[str, object],
) -> None:
    worksheet.set_column("A:A", 8)
    worksheet.set_column("B:C", 13)
    worksheet.set_column("D:E", 11)
    worksheet.set_column("F:F", 16)
    worksheet.set_column("G:H", 28)
    worksheet.set_column("I:I", 12)
    worksheet.set_column("J:M", 14)
    worksheet.set_column("N:P", 20)
    worksheet.set_column("Q:Q", 42)
    worksheet.set_column("R:T", 24)
    worksheet.set_column("U:U", 30)
    worksheet.set_column("V:V", 32)

    worksheet.merge_range("A1:V1", "TRAZABILIDAD DE LA LIQUIDACIÓN", formats["title"])
    worksheet.write(1, 0, "Fecha de liquidación", formats["label"])
    if resultado.fecha_liquidacion:
        worksheet.write_datetime(1, 1, resultado.fecha_liquidacion, formats["date"])
    else:
        worksheet.write(1, 1, "No indicada (se usó el IPC más reciente)", formats["cell"])
    worksheet.write(1, 3, "Fuente IPC actual", formats["label"])
    worksheet.write(1, 4, resultado.ipc_actual_fuente or "N/D", formats["cell"])
    worksheet.write(1, 6, "Período IPC actual", formats["label"])
    worksheet.write(1, 7, resultado.ipc_actual_periodo or "N/D", formats["cell"])
    worksheet.write(1, 9, "Registros IPC", formats["label"])
    if ipc_info:
        worksheet.write_number(1, 10, ipc_info.total_registros, formats["int"])
    else:
        worksheet.write(1, 10, "N/D", formats["cell"])

    worksheet.write(2, 0, "Convención de días", formats["label"])
    worksheet.write(2, 1, "Días calendario reales (incluye extremos)", formats["cell"])
    worksheet.write(2, 3, "PPC", formats["label"])
    worksheet.write_number(2, 4, float(resultado.ppc), formats["percent"])
    worksheet.write(2, 6, "Divisor mensual a semanal", formats["label"])
    worksheet.write_number(2, 7, 4.345, formats["num"])
    worksheet.write(2, 9, "Fórmula ISV", formats["label"])
    worksheet.write(2, 10, "SBC x SC x PPC", formats["cell"])

    if resultado.advertencias:
        worksheet.write(3, 0, "Advertencias del cálculo", formats["label"])
        worksheet.merge_range(3, 1, 3, 6, "\n".join(resultado.advertencias), formats["cell"])

    headers = [
        "Año",
        "Fecha inicio",
        "Fecha fin",
        "Días calendario",
        "Semanas",
        "IBL reportado",
        "Método IBL",
        "Evidencia IBL",
        "Revisión IBL",
        "IPC inicial (promedio anual)",
        "Meses IPC inicial",
        "Período IPC actual",
        "IPC actual",
        "Factor de indexación",
        "IBC mensual actualizado",
        "IBC semanal actualizado",
        "Advertencias IPC",
        "Origen CETIL",
        "Página CETIL",
        "Cargo",
        "Entidad",
        "Documento CETIL",
    ]
    header_row = 5
    for col_num, value in enumerate(headers):
        worksheet.write(header_row, col_num, value, formats["header"])

    annual_rows = cetil_result.filas_liquidables_anuales if cetil_result else []
    for offset, row in enumerate(resultado.periodos):
        excel_row = header_row + 1 + offset
        annual = _match_annual_row(row, annual_rows)
        factor = (
            row.ipc_actual / row.ipc_inicial if row.ipc_inicial else Decimal(0)
        )
        worksheet.write(excel_row, 0, row.anio or row.fecha_inicio.year, formats["cell"])
        worksheet.write_datetime(excel_row, 1, row.fecha_inicio, formats["date"])
        worksheet.write_datetime(excel_row, 2, row.fecha_fin, formats["date"])
        worksheet.write_number(excel_row, 3, row.dias, formats["int"])
        worksheet.write_number(excel_row, 4, float(row.semanas), formats["num"])
        worksheet.write_number(excel_row, 5, _money(row.ibl_reportado), formats["money"])
        worksheet.write(excel_row, 6, _annual_value(annual, "ibl_metodo"), formats["cell"])
        worksheet.write(excel_row, 7, _annual_value(annual, "ibl_evidencia"), formats["cell"])
        worksheet.write(
            excel_row,
            8,
            "Sí" if annual is not None and annual.ibl_requiere_revision else "No",
            formats["cell"],
        )
        worksheet.write_number(excel_row, 9, float(row.ipc_inicial), formats["num"])
        worksheet.write_number(excel_row, 10, row.ipc_meses_usados or 0, formats["int"])
        worksheet.write(excel_row, 11, row.periodo_ipc_actual, formats["cell"])
        worksheet.write_number(excel_row, 12, float(row.ipc_actual), formats["num"])
        worksheet.write_number(excel_row, 13, float(factor), formats["num"])
        worksheet.write_number(excel_row, 14, _money(row.ibc_actualizado), formats["money"])
        worksheet.write_number(
            excel_row, 15, _money(row.ibc_semanal_actualizado), formats["money"]
        )
        worksheet.write(
            excel_row,
            16,
            "\n".join(row.advertencias_ipc) if row.advertencias_ipc else "",
            formats["cell"],
        )
        worksheet.write(excel_row, 17, _annual_value(annual, "periodo_origen"), formats["cell"])
        worksheet.write(excel_row, 18, _annual_value(annual, "fuente_pagina"), formats["cell"])
        worksheet.write(excel_row, 19, row.cargo or _annual_value(annual, "cargo"), formats["cell"])
        worksheet.write(
            excel_row, 20, row.entidad or _annual_value(annual, "entidad"), formats["cell"]
        )
        worksheet.write(
            excel_row,
            21,
            row.documento_cetil or _annual_value(annual, "documento_cetil") or "",
            formats["cell"],
        )

    worksheet.freeze_panes(header_row + 1, 0)


def _match_annual_row(
    row: ResultadoPeriodo,
    annual_rows: list[PeriodoLiquidableAnual],
) -> PeriodoLiquidableAnual | None:
    anio = row.anio or row.fecha_inicio.year
    for annual in annual_rows:
        if (
            annual.anio == anio
            and annual.fecha_inicio == row.fecha_inicio
            and annual.fecha_fin == row.fecha_fin
        ):
            return annual
    for annual in annual_rows:
        if annual.anio == anio:
            return annual
    return None


def _annual_value(annual: PeriodoLiquidableAnual | None, attribute: str) -> object:
    if annual is None:
        return ""
    value = getattr(annual, attribute, None)
    return "" if value is None else value


def _ipc_warnings(resultado: ResultadoLiquidacion) -> list[str]:
    warnings: list[str] = []
    for row in resultado.periodos:
        for warning in row.advertencias_ipc:
            if warning not in warnings:
                warnings.append(warning)
    return warnings
