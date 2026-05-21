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
                    html.Div(
                        [
                            html.Span("Liquidación ISV", className="app-header__eyebrow"),
                            html.H1("AppIndemnizaciones"),
                            html.P(
                                "Liquidación pensional con trazabilidad CETIL, IPC anual y exportación auditables.",
                                className="lead",
                            ),
                        ],
                        className="app-header__content",
                    ),
                    html.Div(
                        [
                            html.Span("Python", className="app-badge"),
                            html.Span("Dash", className="app-badge"),
                            html.Span("CETIL", className="app-badge"),
                        ],
                        className="app-header__meta",
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
                            "Cargar certificado CETIL",
                            [
                                dcc.Store(id="cetil-store"),
                                upload_zone(
                                    "upload-cetil",
                                    hint="Arrastra o selecciona certificado CETIL en PDF",
                                ),
                                html.Div(id="cetil-upload-status", className="mt-3"),
                                html.Div(
                                    [
                                        dbc.Button(
                                            "Agregar periodos CETIL a la tabla",
                                            id="btn-use-cetil-data",
                                            color="secondary",
                                        ),
                                        dbc.Button(
                                            "Limpiar CETIL / Nueva liquidación",
                                            id="btn-limpiar-cetil",
                                            color="secondary",
                                            outline=True,
                                        ),
                                    ],
                                    className="step-actions",
                                ),
                                html.Div(id="cetil-apply-status", className="mt-3"),
                            ],
                            subtitle="Extrae datos revisables. No calcula sin validación manual.",
                        ),
                        md=6,
                    ),
                ],
                className="g-3",
            ),
            step_card(
                3,
                "Datos extraídos del CETIL",
                [
                    html.Div(id="cetil-summary", className="mt-3"),
                ],
                subtitle="Información detectada en encabezado, empleado y entidad empleadora.",
                extra_class="mt-3",
            ),
            step_card(
                4,
                "Cuadro de liquidación anual",
                [
                    dcc.Store(id="periodos-store", data=[]),
                    dcc.Store(id="periodos-import-store"),
                    html.P(
                        "Periodos anualizados desde CETIL. Revise fechas e IBL antes de calcular.",
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
                subtitle="Periodos anualizados desde CETIL. Revise fechas e IBL antes de calcular.",
                extra_class="mt-3",
            ),
            dcc.Store(id="resultado-store"),
            dcc.Loading(
                html.Div(id="resultado-liquidacion", className="mt-4"),
                type="circle",
            ),
            dcc.Download(id="download-liquidacion"),
            html.Footer(
                [
                    html.Span("© 2026 ", className="app-footer__mark"),
                    html.Strong("Javier Andrés Valencia Moreno"),
                    html.Span(". CEO · Colombia ®"),
                ],
                className="app-footer",
            ),
        ],
        fluid=True,
        className="app-shell",
    )
