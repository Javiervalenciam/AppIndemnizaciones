"""
Renderers de tablas para resultados de liquidación.

Funciones presentacionales puras: reciben un `ResultadoLiquidacion` ya
calculado y devuelven nodos Dash. NO calculan nada, NO redondean para
cálculo: solo formatean para mostrar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import dash_bootstrap_components as dbc
from dash import dash_table, html

from app_indemnizaciones.domain.models import ResultadoLiquidacion, ResultadoPeriodo
from app_indemnizaciones.ui.components import metric_card

_CENT = Decimal("0.01")

PERIODOS_COLUMNS = [
    {"name": "ID", "id": "id", "type": "text", "editable": False},
    {"name": "Año", "id": "anio", "type": "text", "editable": False},
    {"name": "Fecha Desde", "id": "fecha_inicio", "type": "text", "editable": True},
    {"name": "Fecha Hasta", "id": "fecha_fin", "type": "text", "editable": True},
    {"name": "IBL Reportado", "id": "ibl_reportado", "type": "text", "editable": True},
    {"name": "Cargo", "id": "cargo", "type": "text", "editable": True},
    {"name": "Entidad", "id": "entidad", "type": "text", "editable": True},
    {"name": "Fuente", "id": "fuente", "presentation": "dropdown", "type": "text", "editable": False},
    {"name": "Observaciones", "id": "observaciones", "type": "text", "editable": False},
    {"name": "Estado", "id": "estado_validacion", "type": "text", "editable": False},
    {"name": "Errores / advertencias", "id": "errores", "type": "text", "editable": False},
]

PERIODOS_STYLE_CONDITIONAL = [
    {
        "if": {"row_index": "odd"},
        "backgroundColor": "rgba(248, 251, 255, 0.56)",
    },
    {
        "if": {"filter_query": "{estado_validacion} = ERROR"},
        "backgroundColor": "rgba(254, 226, 226, 0.72)",
        "color": "#7F1D1D",
    },
    {
        "if": {"filter_query": "{estado_validacion} = ADVERTENCIA"},
        "backgroundColor": "rgba(254, 243, 199, 0.74)",
        "color": "#78350F",
    },
    {
        "if": {"filter_query": "{estado_validacion} = OK"},
        "backgroundColor": "rgba(220, 252, 231, 0.68)",
        "color": "#14532D",
    },
]


def _fmt_money(value: Decimal) -> str:
    quant = value.quantize(_CENT)
    return f"${quant:,.2f}"


def _fmt_decimal(value: Decimal, places: int = 4) -> str:
    return f"{value:,.{places}f}"


def _fmt_percent(value: Decimal) -> str:
    return f"{value * Decimal('100'):.3f}%"


def _fmt_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def build_periodos_table(data: list[dict[str, str]] | None = None) -> dash_table.DataTable:
    return dash_table.DataTable(
        id="periodos-table",
        data=data or [],
        columns=PERIODOS_COLUMNS,
        editable=False,
        row_selectable="multi",
        selected_rows=[],
        page_size=8,
        sort_action="native",
        filter_action="native",
        hidden_columns=["id", "fuente", "observaciones"],
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
        style_table={
            "overflowX": "auto",
            "borderRadius": "18px",
            "background": "rgba(255, 255, 255, 0.58)",
        },
        style_cell={
            "fontFamily": "Poppins, Inter, Roboto, Arial, sans-serif",
            "fontSize": "13px",
            "padding": "12px",
            "textAlign": "left",
            "minWidth": "120px",
            "whiteSpace": "normal",
            "height": "auto",
            "backgroundColor": "rgba(255, 255, 255, 0.42)",
            "border": "0",
            "borderBottom": "1px solid rgba(148, 163, 184, 0.18)",
            "color": "#223047",
        },
        style_header={
            "backgroundColor": "rgba(230, 239, 255, 0.86)",
            "color": "#03346C",
            "fontWeight": "800",
            "border": "0",
            "borderBottom": "1px solid rgba(0, 87, 184, 0.16)",
            "textTransform": "uppercase",
            "letterSpacing": "0",
        },
        style_data={
            "borderBottom": "1px solid rgba(148, 163, 184, 0.18)",
        },
        style_filter={
            "backgroundColor": "rgba(255, 255, 255, 0.76)",
            "border": "0",
            "borderBottom": "1px solid rgba(148, 163, 184, 0.2)",
        },
        style_cell_conditional=[
            {"if": {"column_id": "id"}, "minWidth": "72px", "width": "72px", "maxWidth": "80px"},
            {"if": {"column_id": "anio"}, "minWidth": "72px", "width": "80px", "maxWidth": "96px"},
            {"if": {"column_id": "estado_validacion"}, "minWidth": "96px", "width": "112px"},
            {"if": {"column_id": "errores"}, "minWidth": "260px"},
            {"if": {"column_id": "ibl_reportado"}, "fontWeight": "700"},
        ],
        style_data_conditional=PERIODOS_STYLE_CONDITIONAL,
    )


def _periodo_row(row: ResultadoPeriodo) -> html.Tr:
    warnings = "; ".join(row.advertencias_ipc)
    return html.Tr(
        [
            html.Td(row.anio or row.fecha_inicio.year, className="num"),
            html.Td(_fmt_date(row.fecha_inicio)),
            html.Td(_fmt_date(row.fecha_fin)),
            html.Td(row.dias, className="num"),
            html.Td(_fmt_decimal(row.semanas, 2), className="num"),
            html.Td(_fmt_money(row.ibl_reportado), className="money"),
            html.Td(_fmt_percent(Decimal("0.0227")), className="num"),
            html.Td(_fmt_decimal(row.ipc_inicial, 2), className="num"),
            html.Td(_fmt_decimal(row.ipc_actual, 2), className="num"),
            html.Td(_fmt_money(row.ibc_actualizado), className="money"),
            html.Td(_fmt_money(row.ibc_semanal_actualizado), className="money"),
            html.Td("OK" if not warnings else "ADVERTENCIA"),
            html.Td(warnings),
        ]
    )


def build_resultado_table(resultado: ResultadoLiquidacion) -> html.Table:
    head = html.Thead(
        html.Tr(
            [
                html.Th("Año"),
                html.Th("Fecha Desde"),
                html.Th("Fecha Hasta"),
                html.Th("No. Días"),
                html.Th("No. Sem."),
                html.Th("IBL Reportado"),
                html.Th("% Apl."),
                html.Th("IPC Inicial"),
                html.Th("IPC Actual"),
                html.Th("Indexación IBC Mensual"),
                html.Th("IBC Semanal Actualizado"),
                html.Th("Estado"),
                html.Th("Errores / Advertencias"),
            ]
        )
    )
    body = html.Tbody([_periodo_row(row) for row in resultado.periodos])
    return html.Table([head, body], className="resultado-table")


def build_totales_row(resultado: ResultadoLiquidacion) -> dbc.Row:
    return dbc.Row(
        [
            dbc.Col(
                metric_card("LIQUIDACIÓN DE APORTES", _fmt_money(resultado.isv), accent=True, helper="SBC x SC x PPC"),
                md=12,
                lg=4,
                className="mb-3",
            ),
            dbc.Col(metric_card("DÍAS EN TOTAL", f"{resultado.total_dias:,}"), md=6, lg=2, className="mb-3"),
            dbc.Col(metric_card("SC / SEMANAS", _fmt_decimal(resultado.sc, 2)), md=6, lg=2, className="mb-3"),
            dbc.Col(metric_card("PPC", _fmt_percent(resultado.ppc)), md=6, lg=2, className="mb-3"),
            dbc.Col(metric_card("SBC", _fmt_money(resultado.sbc)), md=6, lg=2, className="mb-3"),
        ],
        className="g-3 mt-2",
    )
