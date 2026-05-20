from __future__ import annotations

import io
from decimal import Decimal

import pandas as pd

from app_indemnizaciones.domain.models import ResultadoLiquidacion


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def build_liquidacion_xlsx(resultado: ResultadoLiquidacion) -> bytes:
    """Return formatted XLSX bytes for Dash download."""
    output = io.BytesIO()

    rows = []
    for idx, row in enumerate(resultado.periodos, start=1):
        rows.append(
            {
                "No.": idx,
                "Fecha Desde": row.fecha_inicio,
                "Fecha Hasta": row.fecha_fin,
                "No. Días": row.dias,
                "No. Sem.": float(row.semanas),
                "IBL Reportado": _money(row.ibl_reportado),
                "IPC Inicial": float(row.ipc_inicial),
                "IPC Actual": float(row.ipc_actual),
                "IBC Actualizado": _money(row.ibc_actualizado),
                "IBC Semanal Actualizado": _money(row.ibc_semanal_actualizado),
            }
        )

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Liquidación", index=False, startrow=5)
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
        int_fmt = workbook.add_format({"num_format": "#,##0", "border": 1})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1})
        cell_fmt = workbook.add_format({"border": 1})
        total_label_fmt = workbook.add_format({"bold": True, "bg_color": "#E2F0D9", "border": 1})
        total_value_fmt = workbook.add_format({"bold": True, "num_format": "$ #,##0.00", "border": 1})

        worksheet.merge_range("A1:J1", "LIQUIDACIÓN DE INDEMNIZACIÓN SUSTITUTIVA DE VEJEZ", title_fmt)
        worksheet.write("A3", "PPC")
        worksheet.write_number("B3", float(resultado.ppc), num_fmt)
        worksheet.write("D3", "SC")
        worksheet.write_number("E3", float(resultado.sc), num_fmt)
        worksheet.write("G3", "SBC")
        worksheet.write_number("H3", _money(resultado.sbc), money_fmt)

        for col_num, value in enumerate(df.columns.values):
            worksheet.write(5, col_num, value, header_fmt)

        widths = [6, 14, 14, 12, 12, 16, 12, 12, 18, 24]
        for col_num, width in enumerate(widths):
            worksheet.set_column(col_num, col_num, width)

        first_data_row = 6
        last_data_row = first_data_row + len(df) - 1
        for row_num in range(first_data_row, last_data_row + 1):
            worksheet.set_row(row_num, 20)
            worksheet.write(row_num, 0, df.iloc[row_num - first_data_row, 0], cell_fmt)
            worksheet.write_datetime(row_num, 1, df.iloc[row_num - first_data_row, 1], date_fmt)
            worksheet.write_datetime(row_num, 2, df.iloc[row_num - first_data_row, 2], date_fmt)
            worksheet.write_number(row_num, 3, df.iloc[row_num - first_data_row, 3], int_fmt)
            worksheet.write_number(row_num, 4, df.iloc[row_num - first_data_row, 4], num_fmt)
            worksheet.write_number(row_num, 5, df.iloc[row_num - first_data_row, 5], money_fmt)
            worksheet.write_number(row_num, 6, df.iloc[row_num - first_data_row, 6], num_fmt)
            worksheet.write_number(row_num, 7, df.iloc[row_num - first_data_row, 7], num_fmt)
            worksheet.write_number(row_num, 8, df.iloc[row_num - first_data_row, 8], money_fmt)
            worksheet.write_number(row_num, 9, df.iloc[row_num - first_data_row, 9], money_fmt)

        total_row = last_data_row + 3
        worksheet.write(total_row, 0, "DÍAS EN TOTAL", total_label_fmt)
        worksheet.write_number(total_row, 1, resultado.total_dias, int_fmt)
        worksheet.write(total_row + 1, 0, "SC", total_label_fmt)
        worksheet.write_number(total_row + 1, 1, float(resultado.sc), num_fmt)
        worksheet.write(total_row + 2, 0, "SBC", total_label_fmt)
        worksheet.write_number(total_row + 2, 1, _money(resultado.sbc), total_value_fmt)
        worksheet.write(total_row + 3, 0, "ISV", total_label_fmt)
        worksheet.write_number(total_row + 3, 1, _money(resultado.isv), total_value_fmt)

        worksheet.freeze_panes(6, 0)

    return output.getvalue()
