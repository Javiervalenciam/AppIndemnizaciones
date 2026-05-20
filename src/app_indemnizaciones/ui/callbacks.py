from __future__ import annotations

import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dcc, html, no_update

from app_indemnizaciones.domain.models import PeriodoLaborado
from app_indemnizaciones.services.excel_exporter import build_liquidacion_xlsx
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService
from app_indemnizaciones.services.serialization import resultado_from_dict, resultado_to_dict
from app_indemnizaciones.ui.tables import build_resultado_table, build_totales_row
from app_indemnizaciones.utils.dates import parse_date
from app_indemnizaciones.utils.number_format import parse_decimal


def register_callbacks(app) -> None:  # noqa: ANN001
    @app.callback(
        Output("ipc-status", "children"),
        Output("ipc-store", "data"),
        Input("upload-ipc", "contents"),
        State("upload-ipc", "filename"),
        prevent_initial_call=True,
    )
    def load_ipc(contents: str, filename: str):
        try:
            repo = IpcRepository.from_upload_contents(contents, filename)
            summary = repo.summary()
            data = [
                {"periodo": row.periodo, "fecha": row.fecha.isoformat(), "indice": str(row.indice)}
                for row in repo.registros
            ]
            return (
                dbc.Alert(
                    f"IPC cargado: {summary.total_registros} registros. "
                    f"Rango {summary.periodo_minimo} a {summary.periodo_maximo}. "
                    f"IPC actual detectado: {summary.ipc_actual}.",
                    color="success",
                ),
                data,
            )
        except Exception as exc:  # UI boundary
            return dbc.Alert(str(exc), color="danger"), no_update

    @app.callback(
        Output("periodos-container", "children"),
        Input("btn-add-periodo", "n_clicks"),
        State("periodos-container", "children"),
        prevent_initial_call=True,
    )
    def add_periodo(n_clicks: int, children: list | None):
        children = children if isinstance(children, list) else []
        idx = len(children)
        row = dbc.Row(
            [
                dbc.Col(dcc.DatePickerSingle(id={"type": "periodo-desde", "index": idx}, placeholder="Desde"), md=3),
                dbc.Col(dcc.DatePickerSingle(id={"type": "periodo-hasta", "index": idx}, placeholder="Hasta"), md=3),
                dbc.Col(dbc.Input(id={"type": "periodo-ibl", "index": idx}, placeholder="IBL / salario base"), md=3),
                dbc.Col(dbc.Input(id={"type": "periodo-cargo", "index": idx}, placeholder="Cargo opcional"), md=3),
            ],
            className="periodo-row g-2",
        )
        children.append(row)
        return children

    @app.callback(
        Output("resultado-liquidacion", "children"),
        Output("resultado-store", "data"),
        Input("btn-calcular", "n_clicks"),
        State("ipc-store", "data"),
        State({"type": "periodo-desde", "index": ALL}, "date"),  # type: ignore[name-defined]
        State({"type": "periodo-hasta", "index": ALL}, "date"),  # type: ignore[name-defined]
        State({"type": "periodo-ibl", "index": ALL}, "value"),  # type: ignore[name-defined]
        State({"type": "periodo-cargo", "index": ALL}, "value"),  # type: ignore[name-defined]
        prevent_initial_call=True,
    )
    def calcular(n_clicks, ipc_data, fechas_desde, fechas_hasta, ibls, cargos):
        if not ipc_data:
            return dbc.Alert("Primero cargue el archivo IPC.", color="warning"), no_update

        try:
            repo = IpcRepository.from_dataframe(pd.DataFrame(ipc_data))
            periodos = []
            for desde, hasta, ibl, cargo in zip(fechas_desde, fechas_hasta, ibls, cargos, strict=False):
                if not desde or not hasta or not ibl:
                    continue
                periodos.append(
                    PeriodoLaborado(
                        fecha_inicio=parse_date(desde),
                        fecha_fin=parse_date(hasta),
                        ibl_reportado=parse_decimal(ibl),
                        cargo=cargo,
                    )
                )

            resultado = LiquidacionService(repo).calcular(periodos)
            content = html.Div(
                [
                    html.Div(
                        [
                            html.Span("4", className="step-card__badge"),
                            html.Div(
                                [
                                    html.H3("Resultado de liquidación", className="step-card__title"),
                                    html.P(
                                        "Detalle por periodo y totales consolidados.",
                                        className="step-card__subtitle",
                                    ),
                                ]
                            ),
                        ],
                        className="step-card__header",
                    ),
                    build_resultado_table(resultado),
                    build_totales_row(resultado),
                    html.Div(
                        [
                            dbc.Button("Descargar Excel", id="btn-download", color="success"),
                        ],
                        className="step-actions",
                    ),
                ],
                className="step-card",
            )
            return content, resultado_to_dict(resultado)
        except Exception as exc:
            return dbc.Alert(str(exc), color="danger"), no_update

    @app.callback(
        Output("download-liquidacion", "data"),
        Input("btn-download", "n_clicks"),
        State("resultado-store", "data"),
        prevent_initial_call=True,
    )
    def descargar_excel(n_clicks, resultado_data):
        if not resultado_data:
            return no_update
        resultado = resultado_from_dict(resultado_data)
        xlsx = build_liquidacion_xlsx(resultado)
        return dcc.send_bytes(xlsx, "liquidacion_isv.xlsx")
