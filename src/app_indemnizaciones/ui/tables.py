"""
Renderers de tablas para resultados de liquidación.

Funciones presentacionales puras: reciben un `ResultadoLiquidacion` ya
calculado y devuelven nodos Dash. NO calculan nada, NO redondean para
cálculo: solo formatean para mostrar.
"""

from __future__ import annotations

from decimal import Decimal

import dash_bootstrap_components as dbc
from dash import dash_table, html

from app_indemnizaciones.domain.models import ResultadoLiquidacion, ResultadoPeriodo
from app_indemnizaciones.ui.components import metric_card

_CENT = Decimal("0.01")

PERIODOS_COLUMNS = [
    {"name": "ID", "id": "id", "type": "text", "editable": False},
    {"name": "Fecha inicio", "id": "fecha_inicio", "type": "text"},
    {"name": "Fecha fin", "id": "fecha_fin", "type": "text"},
    {"name": "IBL reportado", "id": "ibl_reportado", "type": "text"},
    {"name": "Cargo", "id": "cargo", "type": "text"},
    {"name": "Entidad", "id": "entidad", "type": "text"},
    {"name": "Fuente", "id": "fuente", "presentation": "dropdown", "type": "text"},
    {"name": "Observaciones", "id": "observaciones", "type": "text"},
    {"name": "Estado", "id": "estado_validacion", "type": "text", "editable": False},
    {"name": "Errores / advertencias", "id": "errores", "type": "text", "editable": False},
]

PERIODOS_STYLE_CONDITIONAL = [
    {
        "if": {"filter_query": "{estado_validacion} = ERROR"},
        "backgroundColor": "#FCE8E6",
        "color": "#7A1B15",
    },
    {
        "if": {"filter_query": "{estado_validacion} = ADVERTENCIA"},
        "backgroundColor": "#FFF4E0",
        "color": "#6F4200",
    },
    {
        "if": {"filter_query": "{estado_validacion} = OK"},
        "backgroundColor": "#E6F4EA",
        "color": "#0F5F2A",
    },
]


def _fmt_money(value: Decimal) -> str:
    quant = value.quantize(_CENT)
    return f"${quant:,.2f}"


def _fmt_decimal(value: Decimal, places: int = 4) -> str:
    return f"{value:,.{places}f}"


def build_periodos_table(data: list[dict[str, str]] | None = None) -> dash_table.DataTable:
    return dash_table.DataTable(
        id="periodos-table",
        data=data or [],
        columns=PERIODOS_COLUMNS,
        editable=True,
        row_selectable="multi",
        selected_rows=[],
        page_size=8,
        sort_action="native",
        filter_action="native",
        dropdown={
            "fuente": {
                "options": [
                    {"label": "manual", "value": "manual"},
                    {"label": "cetil", "value": "cetil"},
                    {"label": "importado", "value": "importado"},
                ]
            }
        },
        style_as_list_view=True,
        style_table={"overflowX": "auto"},
        style_cell={
            "fontFamily": "Roboto, Helvetica Neue, Arial, sans-serif",
            "fontSize": "13px",
            "padding": "10px",
            "textAlign": "left",
            "minWidth": "120px",
            "whiteSpace": "normal",
            "height": "auto",
        },
        style_header={
            "backgroundColor": "#E6EEF7",
            "color": "#002247",
            "fontWeight": "600",
            "borderBottom": "1px solid #E1E5EB",
        },
        style_data={
            "borderBottom": "1px solid #ECEFF3",
        },
        style_cell_conditional=[
            {"if": {"column_id": "id"}, "minWidth": "72px", "width": "72px", "maxWidth": "80px"},
            {"if": {"column_id": "estado_validacion"}, "minWidth": "96px", "width": "112px"},
            {"if": {"column_id": "errores"}, "minWidth": "260px"},
        ],
        style_data_conditional=PERIODOS_STYLE_CONDITIONAL,
    )


def _periodo_row(row: ResultadoPeriodo, idx: int) -> html.Tr:
    return html.Tr(
        [
            html.Td(idx, className="num"),
            html.Td(row.fecha_inicio.isoformat()),
            html.Td(row.fecha_fin.isoformat()),
            html.Td(row.dias, className="num"),
            html.Td(_fmt_decimal(row.semanas, 4), className="num"),
            html.Td(_fmt_money(row.ibl_reportado), className="money"),
            html.Td(row.periodo_ipc_inicial),
            html.Td(_fmt_decimal(row.ipc_inicial, 4), className="num"),
            html.Td(row.periodo_ipc_actual),
            html.Td(_fmt_decimal(row.ipc_actual, 4), className="num"),
            html.Td(_fmt_money(row.ibc_actualizado), className="money"),
            html.Td(_fmt_money(row.ibc_semanal_actualizado), className="money"),
        ]
    )


def build_resultado_table(resultado: ResultadoLiquidacion) -> html.Table:
    head = html.Thead(
        html.Tr(
            [
                html.Th("#"),
                html.Th("Desde"),
                html.Th("Hasta"),
                html.Th("Días"),
                html.Th("Semanas"),
                html.Th("IBL Reportado"),
                html.Th("Periodo IPC inicial"),
                html.Th("IPC inicial"),
                html.Th("Periodo IPC actual"),
                html.Th("IPC actual"),
                html.Th("IBC actualizado"),
                html.Th("IBC semanal actualizado"),
            ]
        )
    )
    body = html.Tbody(
        [_periodo_row(row, idx) for idx, row in enumerate(resultado.periodos, start=1)]
    )
    return html.Table([head, body], className="resultado-table")


def build_totales_row(resultado: ResultadoLiquidacion) -> dbc.Row:
    return dbc.Row(
        [
            dbc.Col(metric_card("Días totales", f"{resultado.total_dias:,}"), md=3, className="mb-3"),
            dbc.Col(metric_card("SC (semanas)", _fmt_decimal(resultado.sc, 4)), md=3, className="mb-3"),
            dbc.Col(metric_card("SBC", _fmt_money(resultado.sbc)), md=3, className="mb-3"),
            dbc.Col(metric_card("ISV", _fmt_money(resultado.isv), accent=True), md=3, className="mb-3"),
        ],
        className="g-3 mt-2",
    )
