"""
Renderers de tablas para resultados de liquidación.

Funciones presentacionales puras: reciben un `ResultadoLiquidacion` ya
calculado y devuelven nodos Dash. NO calculan nada, NO redondean para
cálculo: solo formatean para mostrar.
"""

from __future__ import annotations

from decimal import Decimal

import dash_bootstrap_components as dbc
from dash import html

from app_indemnizaciones.domain.models import ResultadoLiquidacion, ResultadoPeriodo
from app_indemnizaciones.ui.components import metric_card

_CENT = Decimal("0.01")


def _fmt_money(value: Decimal) -> str:
    quant = value.quantize(_CENT)
    return f"${quant:,.2f}"


def _fmt_decimal(value: Decimal, places: int = 4) -> str:
    return f"{value:,.{places}f}"


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
