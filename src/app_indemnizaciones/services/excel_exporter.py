from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app_indemnizaciones.config import MONTHLY_TO_WEEKLY_DIVISOR
from app_indemnizaciones.domain.models import ResultadoLiquidacion, ResultadoPeriodo
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    PeriodoLiquidableAnual,
)
from app_indemnizaciones.services.excel_report_theme import (
    LIQUIDACION_COLUMNS,
    LIQUIDACION_LAST_COLUMN,
    LIQUIDACION_LAYOUT,
    ReportPalette,
    apply_print_setup,
    build_formats,
    text_height,
    wrapped_row_height,
    write_merged,
    write_merged_value,
)
from app_indemnizaciones.services.ipc_loader import IpcRepository

TITLE = "LIQUIDACIÓN DE INDEMNIZACIÓN SUSTITUTIVA DE VEJEZ"
SUBTITLE = (
    "Certificado de Información Laboral (CETIL) · Indexación con IPC histórico · "
    "Días calendario reales inclusivos"
)

TABLE_HEADERS = (
    "AÑO",
    "FECHA\nDESDE",
    "FECHA\nHASTA",
    "No.\nDÍAS",
    "No.\nSEMANAS",
    "IBL\nREPORTADO",
    "PPC\nAPLICADO",
    "IPC\nINICIAL",
    "IPC\nACTUAL",
    "IBC MENSUAL\nACTUALIZADO",
    "IBC SEMANAL\nACTUALIZADO",
)

# El PPC vive en la tarjeta KPI G13:H13 y el divisor en el campo I9:K9.
# Las fórmulas los referencian para que exista una sola fuente en el libro.
PPC_KPI_COLUMN = 6
DIVISOR_VALUE_COLUMN = 8

TRACEABILITY_COLUMNS: tuple[int, ...] = (
    7,
    12,
    12,
    8,
    9,
    14,
    20,
    30,
    8,
    11,
    8,
    11,
    11,
    9,
    15,
    15,
    32,
    20,
    8,
    22,
    20,
    28,
)
TRACEABILITY_LAST_COLUMN = len(TRACEABILITY_COLUMNS) - 1
TRACEABILITY_HEADER_ROW = 5
TRACEABILITY_DIVISOR_ROW = 3
TRACEABILITY_DIVISOR_COLUMN = 15
# El anexo se imprime a dos páginas de ancho: el título se limita a la primera.
TRACEABILITY_FIRST_PAGE_COLUMN = 12

TRACEABILITY_HEADERS = (
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
)


@dataclass(frozen=True)
class IpcExportInfo:
    ipc_actual: Decimal
    fecha_ipc_actual: date
    total_registros: int
    periodo: str = ""


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
    """Genera el XLSX de liquidación con fórmulas y valor cacheado del backend.

    Decisión ``DEC-EXCEL-002``: el backend sigue siendo la única fuente del
    resultado. Cada celda calculada conserva la fórmula de Excel que explica la
    operación, pero se escribe con el valor ya calculado por el motor como
    valor cacheado. Así el libro se ve idéntico antes de recalcular y Excel
    puede recalcular con los mismos insumos sin producir un resultado distinto.

    Las fórmulas se escriben en sintaxis OOXML (``SUM``, ``AVERAGE``) porque
    Excel en español las localiza al mostrarlas. Escribir ``SUMA`` o
    ``PROMEDIO`` directamente produciría ``#NAME?``.
    """
    output = io.BytesIO()

    with _ExcelWorkbook(output) as writer:
        workbook = writer.book
        palette = ReportPalette()
        formats = build_formats(workbook, palette)
        worksheet = workbook.add_worksheet("Liquidación")
        traceability = workbook.add_worksheet("Trazabilidad")
        worksheet.set_tab_color(palette.brand)
        traceability.set_tab_color(palette.muted)

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


def _write_liquidacion_sheet(
    worksheet,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    *,
    cetil_result: CetilExtractionResult | None,
    ipc_info: IpcExportInfo | None,
    formats: dict[str, object],
) -> None:
    periods = list(resultado.periodos)
    if not periods:
        raise ValueError("La liquidación no contiene periodos para exportar.")
    layout = LIQUIDACION_LAYOUT

    for index, width in enumerate(LIQUIDACION_COLUMNS):
        worksheet.set_column(index, index, width)

    _write_title(worksheet, layout, formats)
    _write_metadata(
        worksheet,
        layout,
        resultado,
        cetil_result=cetil_result,
        ipc_info=ipc_info,
        formats=formats,
    )
    _write_kpis(worksheet, layout, resultado, formats)
    _write_annual_table(worksheet, layout, resultado, formats)
    _write_totals(worksheet, layout, resultado, formats)

    notes_row, warning_text = _write_notes(
        worksheet,
        layout,
        resultado,
        ipc_info=ipc_info,
        formats=formats,
    )
    last_row = notes_row
    if warning_text:
        warning_row = notes_row + 1
        write_merged(
            worksheet,
            warning_row,
            0,
            LIQUIDACION_LAST_COLUMN,
            warning_text,
            formats["warning"],
        )
        worksheet.set_row(
            warning_row,
            text_height(warning_text, chars_per_line=165, line_height=10, padding=6),
        )
        last_row = warning_row

    apply_print_setup(
        worksheet,
        last_row=last_row,
        last_col=LIQUIDACION_LAST_COLUMN,
        fit_width=1,
        fit_height=1,
        footer_left="AppIndemnizaciones · Reporte de liquidación",
        footer_right="Página &P de &N",
    )


def _write_title(worksheet, layout, formats) -> None:  # noqa: ANN001
    write_merged(
        worksheet,
        layout.title_row,
        0,
        LIQUIDACION_LAST_COLUMN,
        TITLE,
        formats["title"],
    )
    worksheet.set_row(layout.title_row, 26)
    write_merged(
        worksheet,
        layout.subtitle_row,
        0,
        LIQUIDACION_LAST_COLUMN,
        SUBTITLE,
        formats["subtitle"],
    )
    worksheet.set_row(layout.subtitle_row, 14)
    worksheet.set_row(layout.spacer_row, 4)


def _write_metadata(
    worksheet,  # noqa: ANN001
    layout,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    *,
    cetil_result: CetilExtractionResult | None,
    ipc_info: IpcExportInfo | None,
    formats: dict[str, object],
) -> None:
    metadata = cetil_result.metadata if cetil_result else None
    trabajador = cetil_result.trabajador if cetil_result else None
    entidad = cetil_result.entidad_empleadora if cetil_result else None
    first_period = resultado.periodos[0] if resultado.periodos else None
    ipc_actual = (
        ipc_info.ipc_actual
        if ipc_info
        else (first_period.ipc_actual if first_period else None)
    )

    write_merged(
        worksheet,
        layout.data_section_row,
        0,
        5,
        "DATOS DEL TRABAJADOR",
        formats["section"],
    )
    write_merged(
        worksheet,
        layout.data_section_row,
        6,
        LIQUIDACION_LAST_COLUMN,
        "PARÁMETROS DE LIQUIDACIÓN",
        formats["section"],
    )
    worksheet.set_row(layout.data_section_row, 16)

    person_fields = (
        ("Nombre completo", trabajador.nombre_completo if trabajador else None, "text"),
        ("Documento", trabajador.documento if trabajador else None, "text"),
        (
            "Fecha de nacimiento",
            trabajador.fecha_nacimiento if trabajador else None,
            "date",
        ),
        (
            "Entidad empleadora",
            entidad.nombre_entidad_empleadora if entidad else None,
            "text",
        ),
        ("NIT entidad", entidad.nit_entidad_empleadora if entidad else None, "text"),
    )
    parameter_fields = (
        ("Número CETIL", metadata.numero_cetil if metadata else None, "text"),
        (
            "Fecha CETIL",
            metadata.fecha_expedicion_cetil if metadata else None,
            "date",
        ),
        ("Fecha de liquidación", resultado.fecha_liquidacion, "date"),
        ("IPC actual/final", ipc_actual, "number"),
        ("Divisor semanal", MONTHLY_TO_WEEKLY_DIVISOR, "number"),
    )

    for index, (label, value, kind) in enumerate(person_fields):
        row = layout.first_field_row + index
        write_merged(worksheet, row, 0, 1, label, formats["field_label"])
        _write_field_value(
            worksheet,
            row,
            2,
            5,
            value,
            kind,
            formats,
            placeholder="No disponible",
        )
        worksheet.set_row(row, 15)

    for index, (label, value, kind) in enumerate(parameter_fields):
        row = layout.first_field_row + index
        write_merged(worksheet, row, 6, 7, label, formats["field_label"])
        placeholder = "No indicada" if kind == "date" else "No disponible"
        _write_field_value(
            worksheet,
            row,
            8,
            LIQUIDACION_LAST_COLUMN,
            value,
            kind,
            formats,
            placeholder=placeholder,
        )


def _write_field_value(
    worksheet,  # noqa: ANN001
    row: int,
    first_col: int,
    last_col: int,
    value: object,
    kind: str,
    formats: dict[str, object],
    *,
    placeholder: str = "No disponible",
) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        write_merged(worksheet, row, first_col, last_col, placeholder, formats["field_value"])
        return
    if kind == "date" and isinstance(value, date):
        write_merged_value(
            worksheet,
            row,
            first_col,
            last_col,
            value,
            formats["field_date"],
            kind="date",
        )
        return
    if kind in {"number", "int", "percent"} and isinstance(value, (int, float, Decimal)):
        write_merged_value(
            worksheet,
            row,
            first_col,
            last_col,
            float(value),
            formats[f"field_{kind}"],
            kind="number",
        )
        return
    write_merged(
        worksheet,
        row,
        first_col,
        last_col,
        str(value),
        formats["field_value"],
    )


def _write_kpis(
    worksheet,  # noqa: ANN001
    layout,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    formats: dict[str, object],
) -> None:
    totals_row = layout.totals_row(len(resultado.periodos))
    isv_formula = (
        f"={_ref(layout.kpi_value_row, 4)}"
        f"*{_ref(layout.kpi_value_row, 2)}"
        f"*{_ref(layout.kpi_value_row, PPC_KPI_COLUMN)}"
    )

    write_merged(
        worksheet,
        layout.kpi_section_row,
        0,
        LIQUIDACION_LAST_COLUMN,
        "RESULTADO DE LA LIQUIDACIÓN",
        formats["section"],
    )
    worksheet.set_row(layout.kpi_section_row, 16)

    cards = (
        (
            0,
            1,
            "DÍAS CALENDARIO",
            "kpi_label",
            "kpi_int",
            f"={_ref(totals_row, 3)}",
            resultado.total_dias,
        ),
        (
            2,
            3,
            "SEMANAS (SC)",
            "kpi_label",
            "kpi_num",
            f"={_ref(totals_row, 4)}",
            float(resultado.sc),
        ),
        (
            4,
            5,
            "SALARIO BASE (SBC)",
            "kpi_label",
            "kpi_money",
            f"={_ref(totals_row, 10)}",
            float(resultado.sbc),
        ),
        (
            6,
            7,
            "PPC APLICADO",
            "kpi_label",
            "kpi_percent",
            None,
            float(resultado.ppc),
        ),
        (
            8,
            10,
            "LIQUIDACIÓN DE APORTES (ISV)",
            "kpi_label_accent",
            "kpi_money_accent",
            isv_formula,
            float(resultado.isv),
        ),
    )

    for first_col, last_col, label, label_format, value_format, formula, cached in cards:
        write_merged(
            worksheet,
            layout.kpi_label_row,
            first_col,
            last_col,
            label,
            formats[label_format],
        )
        write_merged(
            worksheet,
            layout.kpi_value_row,
            first_col,
            last_col,
            "",
            formats[value_format],
        )
        if formula is None:
            worksheet.write_number(
                layout.kpi_value_row,
                first_col,
                float(cached),
                formats[value_format],
            )
        else:
            worksheet.write_formula(
                layout.kpi_value_row,
                first_col,
                formula,
                formats[value_format],
                cached,
            )

    worksheet.set_row(layout.kpi_label_row, 15)
    worksheet.set_row(layout.kpi_value_row, 24)


def _write_annual_table(
    worksheet,  # noqa: ANN001
    layout,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    formats: dict[str, object],
) -> None:
    periods = resultado.periodos
    first_data_row = layout.first_data_row
    divisor_cell = _ref(
        layout.first_field_row + layout.divisor_field_index,
        DIVISOR_VALUE_COLUMN,
        absolute=True,
    )
    ppc_cell = _ref(layout.kpi_value_row, PPC_KPI_COLUMN, absolute=True)

    write_merged(
        worksheet,
        layout.table_section_row,
        0,
        LIQUIDACION_LAST_COLUMN,
        f"DETALLE ANUAL INDEXADO · {len(periods)} PERIODOS",
        formats["section"],
    )
    worksheet.set_row(layout.table_section_row, 16)

    for column, header in enumerate(TABLE_HEADERS):
        worksheet.write(layout.table_header_row, column, header, formats["header"])
    worksheet.set_row(layout.table_header_row, 28)

    for offset, row in enumerate(periods):
        excel_row = first_data_row + offset
        spreadsheet_row = excel_row + 1
        band = offset % 2
        worksheet.write(
            excel_row,
            0,
            row.anio or row.fecha_inicio.year,
            formats[f"cell_center_{band}"],
        )
        worksheet.write_datetime(
            excel_row,
            1,
            row.fecha_inicio,
            formats[f"cell_date_{band}"],
        )
        worksheet.write_datetime(
            excel_row,
            2,
            row.fecha_fin,
            formats[f"cell_date_{band}"],
        )
        worksheet.write_formula(
            excel_row,
            3,
            f"=C{spreadsheet_row}-B{spreadsheet_row}+1",
            formats[f"cell_int_{band}"],
            row.dias,
        )
        worksheet.write_formula(
            excel_row,
            4,
            f"=D{spreadsheet_row}/7",
            formats[f"cell_num_{band}"],
            float(row.semanas),
        )
        worksheet.write_number(
            excel_row,
            5,
            float(row.ibl_reportado),
            formats[f"cell_money_{band}"],
        )
        worksheet.write_formula(
            excel_row,
            6,
            f"={ppc_cell}",
            formats[f"cell_percent_{band}"],
            float(resultado.ppc),
        )
        worksheet.write_number(
            excel_row,
            7,
            float(row.ipc_inicial),
            formats[f"cell_num_{band}"],
        )
        worksheet.write_number(
            excel_row,
            8,
            float(row.ipc_actual),
            formats[f"cell_num_{band}"],
        )
        worksheet.write_formula(
            excel_row,
            9,
            f"=F{spreadsheet_row}*(I{spreadsheet_row}/H{spreadsheet_row})",
            formats[f"cell_money_{band}"],
            float(row.ibc_actualizado),
        )
        worksheet.write_formula(
            excel_row,
            10,
            f"=J{spreadsheet_row}/{divisor_cell}",
            formats[f"cell_money_{band}"],
            float(row.ibc_semanal_actualizado),
        )
        worksheet.set_row(excel_row, 15)


def _write_totals(
    worksheet,  # noqa: ANN001
    layout,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    formats: dict[str, object],
) -> None:
    first_data_row = layout.first_data_row
    last_data_row = first_data_row + len(resultado.periodos) - 1
    totals_row = layout.totals_row(len(resultado.periodos))

    write_merged(
        worksheet,
        totals_row,
        0,
        2,
        "TOTALES DEL PERÍODO",
        formats["total_text"],
    )
    for column in range(3, LIQUIDACION_LAST_COLUMN + 1):
        worksheet.write_blank(totals_row, column, None, formats["total_blank"])

    worksheet.write_formula(
        totals_row,
        3,
        f"=SUM(D{first_data_row + 1}:D{last_data_row + 1})",
        formats["total_int"],
        resultado.total_dias,
    )
    worksheet.write_formula(
        totals_row,
        4,
        f"=D{totals_row + 1}/7",
        formats["total_num"],
        float(resultado.sc),
    )
    worksheet.write(totals_row, 9, "SBC", formats["total_text"])
    worksheet.write_formula(
        totals_row,
        10,
        f"=AVERAGE(K{first_data_row + 1}:K{last_data_row + 1})",
        formats["total_money"],
        float(resultado.sbc),
    )
    worksheet.set_row(totals_row, 18)


def _write_notes(
    worksheet,  # noqa: ANN001
    layout,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    *,
    ipc_info: IpcExportInfo | None,
    formats: dict[str, object],
) -> tuple[int, str]:
    notes_row = layout.notes_row(len(resultado.periodos))
    text = _notes_text(resultado, ipc_info)
    write_merged(
        worksheet,
        notes_row,
        0,
        LIQUIDACION_LAST_COLUMN,
        text,
        formats["note"],
    )
    worksheet.set_row(
        notes_row,
        text_height(text, chars_per_line=175, line_height=10, padding=6),
    )
    warnings = _export_warnings(resultado)
    warning_text = "Advertencias: " + " · ".join(warnings) if warnings else ""
    return notes_row, warning_text


def _notes_text(
    resultado: ResultadoLiquidacion,
    ipc_info: IpcExportInfo | None,
) -> str:
    source = _ipc_source_label(resultado.ipc_actual_fuente)
    period = resultado.ipc_actual_periodo or "N/D"
    records = f"{ipc_info.total_registros} registros" if ipc_info else "registros N/D"
    return (
        "Fórmulas del reporte: Días = Fecha hasta − Fecha desde + 1 · "
        "Semanas (SC) = Días / 7 · IBC mensual = IBL × (IPC actual / IPC inicial) · "
        "IBC semanal = IBC mensual / divisor semanal · "
        "SBC = promedio de IBC semanal · ISV = SBC × SC × PPC.\n"
        f"Fuente IPC: {source} · Período {period} · {records} · "
        "Días calendario reales inclusivos. Los valores en caché provienen del motor "
        "y las fórmulas usan los mismos insumos."
    )


_IPC_SOURCE_LABELS = {
    "fecha_liquidacion": "fecha de liquidación",
    "ultimo_registro": "último registro disponible",
}


def _ipc_source_label(value: str | None) -> str:
    if not value:
        return "N/D"
    return _IPC_SOURCE_LABELS.get(value, value.replace("_", " "))


def _export_warnings(resultado: ResultadoLiquidacion) -> list[str]:
    warnings = list(resultado.advertencias)
    for row in resultado.periodos:
        for warning in row.advertencias_ipc:
            if warning not in warnings:
                warnings.append(warning)
    return warnings


def _write_traceability_sheet(
    worksheet,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    *,
    cetil_result: CetilExtractionResult | None,
    ipc_info: IpcExportInfo | None,
    formats: dict[str, object],
) -> None:
    for index, width in enumerate(TRACEABILITY_COLUMNS):
        worksheet.set_column(index, index, width)

    write_merged(
        worksheet,
        0,
        0,
        TRACEABILITY_FIRST_PAGE_COLUMN,
        "TRAZABILIDAD DE LA LIQUIDACIÓN",
        formats["annex_title"],
    )
    worksheet.set_row(0, 24)
    write_merged(
        worksheet,
        1,
        0,
        TRACEABILITY_FIRST_PAGE_COLUMN,
        "Auditoría por fila · fuentes IPC, método IBL y procedencia CETIL",
        formats["annex_subtitle"],
    )
    worksheet.set_row(1, 13)

    _write_traceability_parameters(worksheet, resultado, ipc_info, formats)

    warnings = _export_warnings(resultado)
    if warnings:
        write_merged(worksheet, 4, 0, 1, "Advertencias", formats["field_label"])
        warning_text = "\n".join(warnings)
        write_merged(
            worksheet,
            4,
            2,
            TRACEABILITY_LAST_COLUMN,
            warning_text,
            formats["warning"],
        )
        worksheet.set_row(
            4,
            text_height(warning_text, chars_per_line=260, line_height=10, padding=6),
        )
    else:
        worksheet.set_row(4, 6)

    for column, header in enumerate(TRACEABILITY_HEADERS):
        worksheet.write(
            TRACEABILITY_HEADER_ROW,
            column,
            header,
            formats["header"],
        )
    worksheet.set_row(TRACEABILITY_HEADER_ROW, 42)

    trace_divisor_cell = _ref(
        TRACEABILITY_DIVISOR_ROW,
        TRACEABILITY_DIVISOR_COLUMN,
        absolute=True,
    )
    annual_rows = cetil_result.filas_liquidables_anuales if cetil_result else []
    for offset, row in enumerate(resultado.periodos):
        excel_row = TRACEABILITY_HEADER_ROW + 1 + offset
        spreadsheet_row = excel_row + 1
        band = offset % 2
        annual = _match_annual_row(row, annual_rows)
        factor = (
            row.ipc_actual / row.ipc_inicial if row.ipc_inicial else Decimal(0)
        )
        metodo = _annual_value(annual, "ibl_metodo")
        evidencia = _annual_value(annual, "ibl_evidencia")
        row_warnings = "\n".join(row.advertencias_ipc) if row.advertencias_ipc else ""
        origen = _annual_value(annual, "periodo_origen")
        cargo = row.cargo or _annual_value(annual, "cargo")
        entidad = row.entidad or _annual_value(annual, "entidad")
        documento = (
            row.documento_cetil
            or _annual_value(annual, "documento_cetil")
            or ""
        )

        worksheet.write(
            excel_row,
            0,
            row.anio or row.fecha_inicio.year,
            formats[f"cell_center_{band}"],
        )
        worksheet.write_datetime(
            excel_row,
            1,
            row.fecha_inicio,
            formats[f"cell_date_{band}"],
        )
        worksheet.write_datetime(
            excel_row,
            2,
            row.fecha_fin,
            formats[f"cell_date_{band}"],
        )
        worksheet.write_formula(
            excel_row,
            3,
            f"=C{spreadsheet_row}-B{spreadsheet_row}+1",
            formats[f"cell_int_{band}"],
            row.dias,
        )
        worksheet.write_formula(
            excel_row,
            4,
            f"=D{spreadsheet_row}/7",
            formats[f"cell_num_{band}"],
            float(row.semanas),
        )
        worksheet.write_number(
            excel_row,
            5,
            float(row.ibl_reportado),
            formats[f"cell_money_{band}"],
        )
        worksheet.write(excel_row, 6, metodo, formats[f"cell_text_{band}"])
        worksheet.write(excel_row, 7, evidencia, formats[f"cell_text_{band}"])
        worksheet.write(
            excel_row,
            8,
            "Sí" if annual is not None and annual.ibl_requiere_revision else "No",
            formats[f"cell_center_{band}"],
        )
        worksheet.write_number(
            excel_row,
            9,
            float(row.ipc_inicial),
            formats[f"cell_num_{band}"],
        )
        worksheet.write_number(
            excel_row,
            10,
            row.ipc_meses_usados or 0,
            formats[f"cell_int_{band}"],
        )
        worksheet.write(
            excel_row,
            11,
            row.periodo_ipc_actual,
            formats[f"cell_center_{band}"],
        )
        worksheet.write_number(
            excel_row,
            12,
            float(row.ipc_actual),
            formats[f"cell_num_{band}"],
        )
        worksheet.write_formula(
            excel_row,
            13,
            f"=M{spreadsheet_row}/J{spreadsheet_row}",
            formats[f"cell_num_{band}"],
            float(factor),
        )
        worksheet.write_formula(
            excel_row,
            14,
            f"=F{spreadsheet_row}*N{spreadsheet_row}",
            formats[f"cell_money_{band}"],
            float(row.ibc_actualizado),
        )
        worksheet.write_formula(
            excel_row,
            15,
            f"=O{spreadsheet_row}/{trace_divisor_cell}",
            formats[f"cell_money_{band}"],
            float(row.ibc_semanal_actualizado),
        )
        worksheet.write(excel_row, 16, row_warnings, formats[f"cell_text_{band}"])
        worksheet.write(excel_row, 17, origen, formats[f"cell_text_{band}"])
        worksheet.write(
            excel_row,
            18,
            _annual_value(annual, "fuente_pagina"),
            formats[f"cell_center_{band}"],
        )
        worksheet.write(excel_row, 19, cargo, formats[f"cell_text_{band}"])
        worksheet.write(excel_row, 20, entidad, formats[f"cell_text_{band}"])
        worksheet.write(excel_row, 21, documento, formats[f"cell_text_{band}"])
        worksheet.set_row(
            excel_row,
            wrapped_row_height(
                (
                    (metodo, 18),
                    (evidencia, 28),
                    (row_warnings, 28),
                    (origen, 18),
                    (cargo, 16),
                    (entidad, 18),
                    (documento, 20),
                ),
                line_height=10,
                padding=5,
            ),
        )

    last_row = TRACEABILITY_HEADER_ROW + len(resultado.periodos)
    worksheet.freeze_panes(TRACEABILITY_HEADER_ROW + 1, 0)
    worksheet.repeat_rows(TRACEABILITY_HEADER_ROW)
    apply_print_setup(
        worksheet,
        last_row=last_row,
        last_col=TRACEABILITY_LAST_COLUMN,
        fit_width=2,
        fit_height=0,
        footer_left="AppIndemnizaciones · Trazabilidad",
        footer_right="Página &P de &N",
    )


def _write_traceability_parameters(
    worksheet,  # noqa: ANN001
    resultado: ResultadoLiquidacion,
    ipc_info: IpcExportInfo | None,
    formats: dict[str, object],
) -> None:
    # Cada fila combina cuatro pares etiqueta/valor sobre las 22 columnas.
    slots = ((0, 1, 2, 5), (6, 7, 8, 12), (13, 14, 15, 17), (18, 19, 20, 21))
    ppc_cell = _ref(LIQUIDACION_LAYOUT.kpi_value_row, PPC_KPI_COLUMN, absolute=True)
    divisor_cell = _ref(
        LIQUIDACION_LAYOUT.first_field_row + LIQUIDACION_LAYOUT.divisor_field_index,
        DIVISOR_VALUE_COLUMN,
        absolute=True,
    )
    rows = (
        (
            ("Fecha de liquidación", resultado.fecha_liquidacion, "date"),
            ("Fuente IPC actual", _ipc_source_label(resultado.ipc_actual_fuente), "text"),
            ("Período IPC actual", resultado.ipc_actual_periodo or "N/D", "text"),
            ("Registros IPC", ipc_info.total_registros if ipc_info else None, "int"),
        ),
        (
            ("Convención de días", "Días calendario reales inclusivos", "text"),
            ("PPC", float(resultado.ppc), "percent"),
            ("Divisor semanal", MONTHLY_TO_WEEKLY_DIVISOR, "number"),
            ("Fórmula ISV", "SBC × SC × PPC", "text"),
        ),
    )

    for row, fields in zip((2, 3), rows, strict=True):
        for (label_first, label_last, value_first, value_last), (
            label,
            value,
            kind,
        ) in zip(slots, fields, strict=True):
            write_merged(
                worksheet,
                row,
                label_first,
                label_last,
                label,
                formats["field_label"],
            )
            if label == "PPC":
                # Una sola fuente de PPC en el libro: la tarjeta KPI del reporte.
                write_merged(
                    worksheet,
                    row,
                    value_first,
                    value_last,
                    "",
                    formats["field_percent"],
                )
                worksheet.write_formula(
                    row,
                    value_first,
                    f"='Liquidación'!{ppc_cell}",
                    formats["field_percent"],
                    float(value),
                )
            elif label == "Divisor semanal":
                write_merged(
                    worksheet,
                    row,
                    value_first,
                    value_last,
                    "",
                    formats["field_number"],
                )
                worksheet.write_formula(
                    row,
                    value_first,
                    f"='Liquidación'!{divisor_cell}",
                    formats["field_number"],
                    float(value),
                )
            else:
                placeholder = "No indicada" if kind == "date" else "N/D"
                _write_field_value(
                    worksheet,
                    row,
                    value_first,
                    value_last,
                    value,
                    kind,
                    formats,
                    placeholder=placeholder,
                )
        worksheet.set_row(row, 15)


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


def _column_letter(column: int) -> str:
    letters = ""
    column += 1
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _ref(row: int, column: int, *, absolute: bool = False) -> str:
    column_letter = _column_letter(column)
    row_number = row + 1
    if absolute:
        return f"${column_letter}${row_number}"
    return f"{column_letter}{row_number}"
