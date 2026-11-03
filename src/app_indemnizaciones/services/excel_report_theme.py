"""Diseño visual compartido para los libros Excel de AppIndemnizaciones.

Este módulo concentra paleta, tipografía, formatos y primitivas de maquetación
para que el exportador no mezcle cálculo con presentación. Los formatos
numéricos se escriben con la sintaxis OOXML (inglesa); Excel en español los
muestra localizados, por ejemplo ``SUM`` como ``SUMA``. Nunca se escriben
nombres de funciones traducidos dentro del archivo porque Excel los leería como
``#NAME?``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

FONT_NAME = "Arial"


@dataclass(frozen=True)
class ReportPalette:
    """Paleta institucional sobria, pensada para impresión en blanco y negro."""

    ink: str = "#0F2438"
    brand: str = "#173C5C"
    brand_soft: str = "#E8EFF6"
    accent: str = "#0B6B5B"
    accent_soft: str = "#DCEEE9"
    surface: str = "#F5F8FB"
    surface_alt: str = "#EDF2F7"
    border: str = "#C8D3DE"
    border_soft: str = "#DDE5ED"
    muted: str = "#5C6B7A"
    warning_bg: str = "#FFF6E0"
    warning_ink: str = "#7A4F00"
    warning_border: str = "#E6D3A3"
    white: str = "#FFFFFF"


@dataclass(frozen=True)
class ReportLayout:
    """Filas base cero del reporte compacto de una sola hoja."""

    title_row: int = 0
    subtitle_row: int = 1
    spacer_row: int = 2
    data_section_row: int = 3
    first_field_row: int = 4
    field_count: int = 5
    kpi_section_row: int = 10
    kpi_label_row: int = 11
    kpi_value_row: int = 12
    table_section_row: int = 14
    table_header_row: int = 15
    first_data_row: int = 16
    divisor_field_index: int = 4

    def last_field_row(self) -> int:
        return self.first_field_row + self.field_count - 1

    def totals_row(self, period_count: int) -> int:
        return self.first_data_row + period_count

    def notes_row(self, period_count: int) -> int:
        return self.totals_row(period_count) + 1

    def warning_row(self, period_count: int) -> int:
        return self.totals_row(period_count) + 2


LIQUIDACION_LAYOUT = ReportLayout()
LIQUIDACION_COLUMNS: tuple[int, ...] = (8, 13, 13, 9, 10, 16, 9, 12, 12, 18, 18)
LIQUIDACION_LAST_COLUMN = len(LIQUIDACION_COLUMNS) - 1


def build_formats(
    workbook: Any,
    palette: ReportPalette | None = None,
) -> dict[str, Any]:
    """Crea el catálogo de formatos usado por las hojas del libro."""
    colors = palette or ReportPalette()
    font = {"font_name": FONT_NAME, "font_color": colors.ink}
    formats: dict[str, Any] = {}

    formats["title"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 14,
            "font_color": colors.white,
            "bg_color": colors.ink,
            "align": "center",
            "valign": "vcenter",
        }
    )
    formats["subtitle"] = workbook.add_format(
        {
            **font,
            "italic": True,
            "font_size": 8.5,
            "font_color": "#C9D8E6",
            "bg_color": colors.ink,
            "align": "center",
            "valign": "vcenter",
            "bottom": 1,
            "bottom_color": colors.accent,
        }
    )
    # El anexo de trazabilidad se imprime en dos páginas de ancho: si el título
    # ocupara las 22 columnas, la segunda página mostraría una banda vacía.
    formats["annex_title"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 13,
            "font_color": colors.ink,
            "bg_color": colors.white,
            "align": "left",
            "valign": "vcenter",
            "indent": 1,
            "bottom": 2,
            "bottom_color": colors.brand,
        }
    )
    formats["annex_subtitle"] = workbook.add_format(
        {
            **font,
            "italic": True,
            "font_size": 8,
            "font_color": colors.muted,
            "bg_color": colors.white,
            "align": "left",
            "valign": "vcenter",
            "indent": 1,
            "bottom": 1,
            "bottom_color": colors.border,
        }
    )
    formats["section"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 8.5,
            "font_color": colors.white,
            "bg_color": colors.brand,
            "align": "left",
            "valign": "vcenter",
            "indent": 1,
        }
    )

    formats["field_label"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 8,
            "font_color": colors.muted,
            "bg_color": colors.surface,
            "align": "left",
            "valign": "vcenter",
            "indent": 1,
            "bottom": 1,
            "bottom_color": colors.border_soft,
        }
    )
    field_value = {
        **font,
        "font_size": 9,
        "bg_color": colors.white,
        "align": "left",
        "valign": "vcenter",
        "indent": 1,
        "bottom": 1,
        "bottom_color": colors.border_soft,
    }
    formats["field_value"] = workbook.add_format(field_value)
    formats["field_date"] = workbook.add_format(
        {**field_value, "num_format": "dd/mm/yyyy"}
    )
    formats["field_number"] = workbook.add_format(
        {**field_value, "num_format": "#,##0.000"}
    )
    formats["field_int"] = workbook.add_format({**field_value, "num_format": "#,##0"})
    formats["field_percent"] = workbook.add_format(
        {**field_value, "num_format": "0.000%"}
    )

    formats["kpi_label"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 7.5,
            "font_color": colors.muted,
            "bg_color": colors.surface_alt,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "border": 1,
            "border_color": colors.border,
        }
    )
    kpi_value = {
        **font,
        "bold": True,
        "bg_color": colors.white,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
        "border_color": colors.border,
    }
    formats["kpi_int"] = workbook.add_format(
        {**kpi_value, "font_size": 13, "num_format": "#,##0"}
    )
    formats["kpi_num"] = workbook.add_format(
        {**kpi_value, "font_size": 12, "num_format": "#,##0.000"}
    )
    formats["kpi_money"] = workbook.add_format(
        {**kpi_value, "font_size": 12, "num_format": "$ #,##0.00"}
    )
    formats["kpi_percent"] = workbook.add_format(
        {**kpi_value, "font_size": 12, "num_format": "0.000%"}
    )
    formats["kpi_label_accent"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 7.5,
            "font_color": colors.white,
            "bg_color": colors.accent,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "border": 1,
            "border_color": colors.accent,
        }
    )
    formats["kpi_money_accent"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 14,
            "font_color": colors.white,
            "bg_color": colors.accent,
            "num_format": "$ #,##0.00",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": colors.accent,
        }
    )

    formats["header"] = workbook.add_format(
        {
            **font,
            "bold": True,
            "font_size": 7.5,
            "font_color": colors.white,
            "bg_color": colors.brand,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "border": 1,
            "border_color": colors.brand,
        }
    )

    cell_styles: dict[str, dict[str, Any]] = {
        "text": {"align": "left", "indent": 1},
        "center": {"align": "center"},
        "int": {"align": "center", "num_format": "#,##0"},
        "num": {"align": "right", "num_format": "#,##0.000"},
        "money": {"align": "right", "num_format": "$ #,##0.00"},
        "percent": {"align": "center", "num_format": "0.000%"},
        "date": {"align": "center", "num_format": "dd/mm/yyyy"},
    }
    for kind, style in cell_styles.items():
        for band, fill in ((0, colors.white), (1, colors.surface)):
            formats[f"cell_{kind}_{band}"] = workbook.add_format(
                {
                    **font,
                    "font_size": 8.5,
                    "valign": "vcenter",
                    "bg_color": fill,
                    "border": 1,
                    "border_color": colors.border_soft,
                    "text_wrap": kind == "text",
                    **style,
                }
            )

    total_base = {
        **font,
        "bold": True,
        "font_size": 8.5,
        "bg_color": colors.brand_soft,
        "border": 1,
        "border_color": colors.border,
        "top": 2,
        "top_color": colors.brand,
        "valign": "vcenter",
    }
    formats["total_text"] = workbook.add_format(
        {**total_base, "align": "right", "indent": 1}
    )
    formats["total_int"] = workbook.add_format(
        {**total_base, "align": "center", "num_format": "#,##0"}
    )
    formats["total_num"] = workbook.add_format(
        {**total_base, "align": "right", "num_format": "#,##0.000"}
    )
    formats["total_money"] = workbook.add_format(
        {**total_base, "align": "right", "num_format": "$ #,##0.00"}
    )
    formats["total_blank"] = workbook.add_format(total_base)

    formats["note"] = workbook.add_format(
        {
            **font,
            "italic": True,
            "font_size": 7.5,
            "font_color": colors.muted,
            "align": "left",
            "valign": "vcenter",
            "text_wrap": True,
            "indent": 1,
        }
    )
    formats["warning"] = workbook.add_format(
        {
            **font,
            "font_size": 8,
            "font_color": colors.warning_ink,
            "bg_color": colors.warning_bg,
            "align": "left",
            "valign": "vcenter",
            "text_wrap": True,
            "indent": 1,
            "border": 1,
            "border_color": colors.warning_border,
        }
    )
    return formats


def write_merged(
    worksheet: Any,
    row: int,
    first_col: int,
    last_col: int,
    value: object,
    cell_format: Any,
) -> None:
    """Escribe un valor en una celda o en un rango combinado de una fila."""
    if first_col >= last_col:
        worksheet.write(row, first_col, value, cell_format)
    else:
        worksheet.merge_range(row, first_col, row, last_col, value, cell_format)


def write_merged_value(
    worksheet: Any,
    row: int,
    first_col: int,
    last_col: int,
    value: object,
    cell_format: Any,
    *,
    kind: str = "text",
) -> None:
    """Escribe un valor tipado en un rango combinado.

    ``merge_range`` no distingue fechas ni números de forma fiable en todas las
    versiones, por eso se combina el rango vacío y luego se escribe el ancla.
    """
    write_merged(worksheet, row, first_col, last_col, "", cell_format)
    if kind == "date":
        worksheet.write_datetime(row, first_col, value, cell_format)
    elif kind in {"number", "int", "percent"}:
        worksheet.write_number(row, first_col, float(value), cell_format)
    else:
        worksheet.write(row, first_col, value, cell_format)


def text_height(
    text: str,
    *,
    chars_per_line: int,
    line_height: float = 10,
    padding: float = 6,
) -> float:
    """Estima la altura de una fila con texto envuelto en celdas combinadas."""
    lines = sum(
        max(1, math.ceil(len(paragraph) / max(chars_per_line, 1)))
        for paragraph in text.split("\n")
    )
    return lines * line_height + padding


def wrapped_row_height(
    values_and_widths: list[tuple[object, int]],
    *,
    line_height: float = 10,
    padding: float = 5,
) -> float:
    """Estima la altura de una fila de tabla con varias columnas de texto."""
    lines = 1
    for value, width in values_and_widths:
        text = "" if value is None else str(value)
        for paragraph in text.split("\n"):
            lines = max(lines, math.ceil(len(paragraph) / max(width, 1)))
    return lines * line_height + padding


def apply_print_setup(
    worksheet: Any,
    *,
    last_row: int,
    last_col: int,
    fit_width: int = 1,
    fit_height: int = 1,
    vertical_center: bool = False,
    footer_left: str = "",
    footer_right: str = "",
) -> None:
    """Configura la hoja para impresión institucional en carta horizontal.

    El reporte principal usa ``fit_width=1, fit_height=1`` para caber en una
    sola hoja. El anexo de trazabilidad usa ``fit_width=2, fit_height=0``
    porque sus 22 columnas necesitan dos páginas de ancho.
    """
    worksheet.set_landscape()
    worksheet.set_paper(1)  # Carta
    worksheet.set_margins(0.25, 0.25, 0.35, 0.45)
    worksheet.center_horizontally()
    if vertical_center:
        worksheet.center_vertically()
    worksheet.hide_gridlines(2)
    worksheet.fit_to_pages(fit_width, fit_height)
    worksheet.set_zoom(90)
    if last_row >= 0 and last_col >= 0:
        worksheet.print_area(0, 0, last_row, last_col)
    if footer_left or footer_right:
        # Los códigos &P/&N son propios de Excel: no se escapan.
        worksheet.set_footer(
            f'&L&"Arial,Regular"&8{footer_left}&R&"Arial,Regular"&8{footer_right}'
        )
