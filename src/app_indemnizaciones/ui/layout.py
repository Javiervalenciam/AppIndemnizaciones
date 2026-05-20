from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from app_indemnizaciones.ui.components import step_card, upload_zone
from app_indemnizaciones.ui.tables import build_periodos_table


def build_layout() -> html.Div:
    return dbc.Container(
        [
            html.Header(
                [
                    html.H1("AppIndemnizaciones"),
                    html.P(
                        "MVP para importar IPC histórico, validar datos y calcular liquidación.",
                        className="lead",
                    ),
                ],
                className="app-header",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        step_card(
                            1,
                            "IPC histórico",
                            [
                                upload_zone(
                                    "upload-ipc",
                                    hint="Arrastra o selecciona archivo IPC Excel/CSV",
                                ),
                                html.Div(id="ipc-status", className="mt-3"),
                                dcc.Store(id="ipc-store"),
                            ],
                            subtitle="Carga el histórico IPC y valida el último índice detectado.",
                        ),
                        md=6,
                    ),
                    dbc.Col(
                        step_card(
                            2,
                            "Trabajador",
                            [
                                dbc.Input(
                                    id="trabajador-nombre",
                                    placeholder="Nombre",
                                    className="mb-2",
                                ),
                                dbc.Input(
                                    id="trabajador-documento",
                                    placeholder="Documento",
                                    className="mb-2",
                                ),
                            ],
                            subtitle="Datos mínimos para preparar la liquidación.",
                        ),
                        md=6,
                    ),
                ],
                className="g-3",
            ),
            step_card(
                3,
                "Cargar certificado CETIL",
                [
                    dcc.Store(id="cetil-store"),
                    upload_zone(
                        "upload-cetil",
                        hint="Arrastra o selecciona certificado CETIL en PDF",
                    ),
                    html.Div(id="cetil-upload-status", className="mt-3"),
                    html.Div(id="cetil-summary", className="mt-3"),
                    html.Div(
                        [
                            dbc.Button(
                                "Usar datos extraídos en la tabla de periodos",
                                id="btn-use-cetil-data",
                                color="secondary",
                            ),
                        ],
                        className="step-actions",
                    ),
                    html.Div(id="cetil-apply-status", className="mt-3"),
                ],
                subtitle="Extrae datos revisables. No calcula ni reemplaza información manual.",
                extra_class="mt-3",
            ),
            step_card(
                4,
                "Periodos laborados",
                [
                    dcc.Store(id="periodos-store", data=[]),
                    dcc.Store(id="periodos-import-store"),
                    html.P(
                        "Agrega, revisa o corrige los periodos antes de calcular la liquidación.",
                        className="mb-2",
                    ),
                    html.P("Usa fechas en formato AAAA-MM-DD.", className="periodos-help"),
                    html.Div(id="periodos-alert", className="mb-3"),
                    html.Div(
                        [
                            dbc.Button("Agregar periodo", id="btn-add-periodo", color="secondary"),
                            dbc.Button(
                                "Eliminar seleccionado",
                                id="btn-delete-periodo",
                                color="danger",
                                outline=True,
                            ),
                        ],
                        className="periodos-toolbar",
                    ),
                    build_periodos_table(),
                    html.Div(
                        [
                            dbc.Button(
                                "Calcular liquidación",
                                id="btn-calcular",
                                color="primary",
                            ),
                        ],
                        className="step-actions",
                    ),
                ],
                subtitle="Agrega, revisa o corrige los periodos antes de calcular la liquidación.",
                extra_class="mt-3",
            ),
            dcc.Store(id="resultado-store"),
            dcc.Loading(
                html.Div(id="resultado-liquidacion", className="mt-4"),
                type="circle",
            ),
            dcc.Download(id="download-liquidacion"),
        ],
        fluid=True,
        className="app-shell",
    )
