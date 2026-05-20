from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from app_indemnizaciones.ui.components import empty_periodos_placeholder, step_card, upload_zone


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
                "Periodos laborados",
                [
                    html.P("En el MVP inicial se cargan manualmente. Luego se poblarán desde CETIL."),
                    dbc.Button("Agregar periodo", id="btn-add-periodo", color="secondary", className="mb-3"),
                    html.Div(empty_periodos_placeholder(), id="periodos-container"),
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
                subtitle="Revise fechas y salarios antes de calcular.",
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
