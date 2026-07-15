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
                    html.Div("🚀", className="hero-sticker hero-sticker--rocket", **{"aria-hidden": "true"}),
                    html.Div("✓", className="hero-sticker hero-sticker--check", **{"aria-hidden": "true"}),
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
                            html.Span("IPC anual", className="app-badge app-badge--blue"),
                            html.Span("Revisión CETIL", className="app-badge app-badge--green"),
                            html.Span("Exportación auditable", className="app-badge app-badge--violet"),
                        ],
                        className="app-header__meta",
                    ),
                ],
                className="app-header",
                id="inicio",
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
                                dcc.Store(id="ipc-store", storage_type="local"),
                                dcc.Store(id="ipc-summary-store", storage_type="local"),
                            ],
                            subtitle="Carga el histórico IPC y valida el último índice detectado.",
                            status="Pendiente",
                            status_tone="neutral",
                        ),
                        md=6,
                        id="ipc",
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
                            status="Manual",
                            status_tone="info",
                        ),
                        md=6,
                        id="cetil",
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
            html.Div(
                step_card(
                    4,
                    "Cuadro de liquidación anual",
                    [
                        dcc.Store(id="periodos-store", data=[]),
                        dcc.Store(id="periodos-import-store"),
                        html.P(
                            "Periodos coincidentes desde CETIL. Primero fechas e IBL antes de calcular.",
                            className="periodos-help",
                        ),
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
                                dbc.Button(
                                    "Calcular liquidación",
                                    id="btn-calcular",
                                    color="primary",
                                    className="periodos-toolbar__primary",
                                ),
                            ],
                            className="periodos-toolbar",
                        ),
                        build_periodos_table(),
                    ],
                    subtitle="Revise datos extraídos y complete manualmente lo necesario.",
                    status="Revisión",
                    status_tone="info",
                    extra_class="mt-3",
                ),
                id="liquidacion",
            ),
            dcc.Store(id="resultado-store"),
            html.Div(
                [
                    dcc.Loading(
                        html.Div(id="resultado-liquidacion", className="mt-4"),
                        type="circle",
                    ),
                    html.Div(
                        [
                            html.Div("PDF", className="float-sticker float-sticker--pdf", **{"aria-hidden": "true"}),
                            html.Div("▥", className="float-sticker float-sticker--chart", **{"aria-hidden": "true"}),
                        ],
                        className="scene-decor",
                    ),
                ],
                id="resultados",
            ),
            dcc.Download(id="download-liquidacion"),
            html.Footer(
                [
                    html.Div(
                        [
                            html.Span("© 2026 ", className="app-footer__mark"),
                            html.Strong("Javier Andrés Valencia Moreno"),
                            html.Span(". CEO · Colombia ®"),
                        ]
                    ),
                    html.Small(
                        "Huella de desarrollo: Codex · OpenAI · GPT-5.6 Sol y Terra",
                        className="app-footer__credit",
                    ),
                ],
                className="app-footer",
                id="exportar",
            ),
        ],
        fluid=True,
        className="app-shell",
    )
