from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from app_indemnizaciones.domain.models import ResultadoLiquidacion
from app_indemnizaciones.services.cetil_models import CetilExtractionResult
from app_indemnizaciones.services.ipc_loader import IpcRepository


@dataclass(frozen=True)
class IpcExportInfo:
    ipc_actual: Decimal
    fecha_ipc_actual: date
    total_registros: int


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


def build_ipc_export_info(repo: IpcRepository) -> IpcExportInfo:
    current = repo.get_current_ipc()
    return IpcExportInfo(
        ipc_actual=current.indice,
        fecha_ipc_actual=current.fecha,
        total_registros=len(repo.registros),
    )


def build_liquidacion_xlsx(
    resultado: ResultadoLiquidacion,
    *,
    cetil_result: CetilExtractionResult | None = None,
    ipc_info: IpcExportInfo | None = None,
) -> bytes:
    """Return formatted XLSX bytes for Dash download."""
    output = io.BytesIO()

    rows = []
    for row in resultado.periodos:
        rows.append(
            {
                "AÑO": row.anio or row.fecha_inicio.year,
                "FECHA DESDE": row.fecha_inicio,
                "FECHA HASTA": row.fecha_fin,
                "No. Días": row.dias,
                "No. Sem.": float(row.semanas),
                "IBL Reportado": _money(row.ibl_reportado),
                "% Apl.": float(resultado.ppc),
                "IPC Inicial": float(row.ipc_inicial),
                "IPC Actual": float(row.ipc_actual),
                "Indexación IBC Mensual": _money(row.ibc_actualizado),
                "IBC Semanal Actualizado": _money(row.ibc_semanal_actualizado),
            }
        )

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Liquidación", index=False, startrow=12)
        workbook = writer.book
        worksheet = writer.sheets["Liquidación"]

        title_fmt = workbook.add_format(
            {"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"}
        )
        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#D9EAF7", "border": 1, "align": "center", "valign": "vcenter"}
        )
        money_fmt = workbook.add_format({"num_format": "$ #,##0.00", "border": 1})
        num_fmt = workbook.add_format({"num_format": "#,##0.000", "border": 1})
        percent_fmt = workbook.add_format({"num_format": "0.000%", "border": 1})
        int_fmt = workbook.add_format({"num_format": "#,##0", "border": 1})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1})
        cell_fmt = workbook.add_format({"border": 1})
        total_label_fmt = workbook.add_format({"bold": True, "bg_color": "#E2F0D9", "border": 1})
        total_value_fmt = workbook.add_format({"bold": True, "num_format": "$ #,##0.00", "border": 1})
        meta_label_fmt = workbook.add_format({"bold": True, "bg_color": "#F3F6FA", "border": 1})

        worksheet.merge_range("A1:K1", "LIQUIDACIÓN DE INDEMNIZACIÓN SUSTITUTIVA DE VEJEZ", title_fmt)
        _write_cetil_metadata(worksheet, cetil_result, meta_label_fmt, cell_fmt, date_fmt)
        _write_ipc_metadata(worksheet, ipc_info, resultado, meta_label_fmt, cell_fmt, date_fmt, num_fmt)

        for col_num, value in enumerate(df.columns.values):
            worksheet.write(12, col_num, value, header_fmt)

        widths = [8, 14, 14, 12, 12, 16, 10, 12, 12, 22, 24]
        for col_num, width in enumerate(widths):
            worksheet.set_column(col_num, col_num, width)

        first_data_row = 13
        last_data_row = first_data_row + len(df) - 1
        for row_num in range(first_data_row, last_data_row + 1):
            excel_row = row_num + 1
            dias_formula = f"=DAYS360(B{excel_row},C{excel_row})"
            semanas_formula = f"=D{excel_row}/7"
            ibc_formula = f"=F{excel_row}*(I{excel_row}/H{excel_row})"
            ibc_semanal_formula = f"=J{excel_row}/4.345"
            worksheet.set_row(row_num, 20)
            worksheet.write(row_num, 0, df.iloc[row_num - first_data_row, 0], cell_fmt)
            worksheet.write_datetime(row_num, 1, df.iloc[row_num - first_data_row, 1], date_fmt)
            worksheet.write_datetime(row_num, 2, df.iloc[row_num - first_data_row, 2], date_fmt)
            worksheet.write_formula(row_num, 3, dias_formula, int_fmt, df.iloc[row_num - first_data_row, 3])
            worksheet.write_formula(row_num, 4, semanas_formula, num_fmt, df.iloc[row_num - first_data_row, 4])
            worksheet.write_number(row_num, 5, df.iloc[row_num - first_data_row, 5], money_fmt)
            worksheet.write_number(row_num, 6, df.iloc[row_num - first_data_row, 6], percent_fmt)
            worksheet.write_number(row_num, 7, df.iloc[row_num - first_data_row, 7], num_fmt)
            worksheet.write_number(row_num, 8, df.iloc[row_num - first_data_row, 8], num_fmt)
            worksheet.write_formula(row_num, 9, ibc_formula, money_fmt, df.iloc[row_num - first_data_row, 9])
            worksheet.write_formula(
                row_num,
                10,
                ibc_semanal_formula,
                money_fmt,
                df.iloc[row_num - first_data_row, 10],
            )

        total_row = last_data_row + 3
        first_excel_row = first_data_row + 1
        last_excel_row = last_data_row + 1
        total_excel_row = total_row + 1
        sc_excel_row = total_excel_row + 1
        ppc_excel_row = total_excel_row + 2
        sbc_excel_row = total_excel_row + 3
        worksheet.write(total_row, 0, "DÍAS EN TOTAL", total_label_fmt)
        worksheet.write_formula(
            total_row,
            1,
            f"=SUM(D{first_excel_row}:D{last_excel_row})",
            int_fmt,
            resultado.total_dias,
        )
        worksheet.write(total_row + 1, 0, "SC", total_label_fmt)
        worksheet.write_formula(
            total_row + 1,
            1,
            f"=SUM(E{first_excel_row}:E{last_excel_row})",
            num_fmt,
            float(resultado.sc),
        )
        worksheet.write(total_row + 2, 0, "PPC", total_label_fmt)
        worksheet.write_formula(
            total_row + 2,
            1,
            f"=AVERAGE(G{first_excel_row}:G{last_excel_row})",
            percent_fmt,
            float(resultado.ppc),
        )
        worksheet.write(total_row + 3, 0, "SBC", total_label_fmt)
        worksheet.write_formula(
            total_row + 3,
            1,
            f"=AVERAGE(K{first_excel_row}:K{last_excel_row})",
            total_value_fmt,
            _money(resultado.sbc),
        )
        worksheet.write(total_row + 4, 0, "LIQUIDACIÓN DE APORTES", total_label_fmt)
        worksheet.write_formula(
            total_row + 4,
            1,
            f"=B{sbc_excel_row}*B{sc_excel_row}*B{ppc_excel_row}",
            total_value_fmt,
            _money(resultado.isv),
        )
        worksheet.write(total_row + 5, 0, "SBC x SC x PPC", total_label_fmt)

        worksheet.freeze_panes(13, 0)

    return output.getvalue()


def _write_cetil_metadata(
    worksheet,
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
        (
            "Entidad empleadora",
            entidad.nombre_entidad_empleadora if entidad else None,
        ),
        ("NIT entidad", entidad.nit_entidad_empleadora if entidad else None),
    ]
    for index, (label, value) in enumerate(values, start=1):
        worksheet.write(index, 0, label, label_fmt)
        if isinstance(value, date):
            worksheet.write_datetime(index, 1, value, date_fmt)
        else:
            worksheet.write(index, 1, value or "No detectado", cell_fmt)


def _write_ipc_metadata(
    worksheet,
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


def _ipc_warnings(resultado: ResultadoLiquidacion) -> list[str]:
    warnings: list[str] = []
    for row in resultado.periodos:
        for warning in row.advertencias_ipc:
            if warning not in warnings:
                warnings.append(warning)
    return warnings
