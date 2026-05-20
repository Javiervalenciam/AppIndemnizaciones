from __future__ import annotations

import base64
import binascii

import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, ctx, dcc, html, no_update

from app_indemnizaciones.domain.exceptions import CetilExtractionError, InvalidCetilFileError
from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    cetil_result_from_dict,
    cetil_result_to_dict,
)
from app_indemnizaciones.services.excel_exporter import build_liquidacion_xlsx
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.services.liquidacion_service import LiquidacionService
from app_indemnizaciones.services.period_normalizer import (
    cetil_extraction_to_period_rows,
    new_period_row,
    rows_to_periodos_laborados,
)
from app_indemnizaciones.services.serialization import (
    deserialize_periods,
    resultado_from_dict,
    resultado_to_dict,
    serialize_periods,
)
from app_indemnizaciones.ui.tables import (
    PERIODOS_STYLE_CONDITIONAL,
    build_resultado_table,
    build_totales_row,
)
from app_indemnizaciones.utils.validators import validate_period_rows


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
        Output("cetil-store", "data"),
        Output("cetil-upload-status", "children"),
        Input("upload-cetil", "contents"),
        State("upload-cetil", "filename"),
        prevent_initial_call=True,
    )
    def process_cetil_pdf(contents: str, filename: str | None):
        try:
            pdf_bytes = _decode_pdf_upload(contents, filename)
            result = CetilExtractor().extract_from_bytes(pdf_bytes)
            return (
                cetil_result_to_dict(result),
                dbc.Alert(f"CETIL procesado: {filename or 'archivo PDF'}.", color="success"),
            )
        except (CetilExtractionError, InvalidCetilFileError, ValueError) as exc:
            return no_update, dbc.Alert(str(exc), color="danger")

    @app.callback(
        Output("cetil-summary", "children"),
        Input("cetil-store", "data"),
    )
    def show_cetil_summary(cetil_data: dict | None):
        if not cetil_data:
            return None
        return _build_cetil_summary(cetil_result_from_dict(cetil_data))

    @app.callback(
        Output("periodos-import-store", "data"),
        Output("cetil-apply-status", "children"),
        Input("btn-use-cetil-data", "n_clicks"),
        State("cetil-store", "data"),
        prevent_initial_call=True,
    )
    def apply_cetil_periods(n_clicks: int | None, cetil_data: dict | None):
        if not cetil_data:
            return no_update, dbc.Alert("Primero cargue y procese un certificado CETIL.", color="warning")

        result = cetil_result_from_dict(cetil_data)
        rows = cetil_extraction_to_period_rows(result)
        if not rows:
            return no_update, dbc.Alert("No se detectaron periodos certificados para enviar a la tabla.", color="warning")

        return (
            {"rows": rows, "nonce": n_clicks},
            dbc.Alert(
                f"Se agregaron {len(rows)} periodo(s) extraído(s) a la tabla. "
                "Revise IBL y errores antes de calcular.",
                color="info",
            ),
        )

    @app.callback(
        Output("periodos-store", "data"),
        Output("periodos-table", "data"),
        Output("periodos-table", "style_data_conditional"),
        Output("periodos-table", "selected_rows"),
        Output("periodos-alert", "children"),
        Input("btn-add-periodo", "n_clicks"),
        Input("btn-delete-periodo", "n_clicks"),
        Input("periodos-table", "data"),
        Input("periodos-import-store", "data"),
        State("periodos-table", "selected_rows"),
        State("periodos-table", "selected_row_ids"),
        State("periodos-store", "data"),
        prevent_initial_call=True,
    )
    def sync_periodos(
        add_clicks: int | None,
        delete_clicks: int | None,
        table_data: list[dict] | None,
        import_data: dict | None,
        selected_rows: list[int] | None,
        selected_row_ids: list[str] | None,
        store_data: list[dict] | None,
    ):
        trigger = ctx.triggered_id
        rows = deserialize_periods(store_data)

        if trigger == "btn-add-periodo":
            rows.append(new_period_row())
        elif trigger == "btn-delete-periodo":
            rows = _remove_selected_rows(table_data or rows, selected_rows, selected_row_ids)
        elif trigger == "periodos-table":
            rows = table_data or []
        elif trigger == "periodos-import-store" and import_data:
            rows.extend(import_data.get("rows", []))

        serialized = serialize_periods(rows)
        return (
            serialized,
            serialized,
            PERIODOS_STYLE_CONDITIONAL,
            [],
            _build_periodos_alert(serialized),
        )

    @app.callback(
        Output("resultado-liquidacion", "children"),
        Output("resultado-store", "data"),
        Input("btn-calcular", "n_clicks"),
        State("ipc-store", "data"),
        State("periodos-store", "data"),
        prevent_initial_call=True,
    )
    def calcular(n_clicks, ipc_data, periodos_data):
        if not ipc_data:
            return dbc.Alert("Primero cargue el archivo IPC.", color="warning"), no_update

        try:
            validated_rows = validate_period_rows(periodos_data)
            if any(row["estado_validacion"] == "ERROR" for row in validated_rows):
                return (
                    dbc.Alert(
                        "Hay errores críticos en los periodos. "
                        "Corrige las filas marcadas antes de calcular.",
                        color="danger",
                    ),
                    no_update,
                )

            if not validated_rows:
                return dbc.Alert("Agregue al menos un periodo válido antes de calcular.", color="warning"), no_update

            repo = IpcRepository.from_dataframe(pd.DataFrame(ipc_data))
            periodos = rows_to_periodos_laborados(validated_rows)

            resultado = LiquidacionService(repo).calcular(periodos)
            content = html.Div(
                [
                    html.Div(
                        [
                            html.Span("5", className="step-card__badge"),
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


def _remove_selected_rows(
    rows: list[dict],
    selected_rows: list[int] | None,
    selected_row_ids: list[str] | None,
) -> list[dict]:
    selected_ids = {str(row_id) for row_id in selected_row_ids or [] if row_id is not None}
    if selected_ids:
        return [row for row in rows if str(row.get("id")) not in selected_ids]

    selected_indexes = set(selected_rows or [])
    return [row for index, row in enumerate(rows) if index not in selected_indexes]


def _build_periodos_alert(rows: list[dict[str, str]]) -> dbc.Alert | None:
    if not rows:
        return None
    if any(row.get("estado_validacion") == "ERROR" for row in rows):
        return dbc.Alert(
            "Hay errores críticos en los periodos. Corrige las filas marcadas antes de calcular.",
            color="danger",
        )
    if any(row.get("estado_validacion") == "ADVERTENCIA" for row in rows):
        return dbc.Alert(
            "Hay advertencias no bloqueantes. Puedes calcular, pero revisa la información.",
            color="warning",
        )
    return dbc.Alert("Periodos listos para calcular.", color="success")


def _decode_pdf_upload(contents: str | None, filename: str | None) -> bytes:
    if not contents:
        raise InvalidCetilFileError("No se recibió el archivo CETIL.")
    if filename and not filename.lower().endswith(".pdf"):
        raise InvalidCetilFileError("El archivo CETIL debe ser un PDF.")

    try:
        _, encoded = contents.split(",", 1)
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidCetilFileError("No se pudo decodificar el PDF CETIL.") from exc


def _build_cetil_summary(result: CetilExtractionResult) -> html.Div:
    trabajador = result.trabajador
    nombre = trabajador.nombre_completo if trabajador else None
    documento = trabajador.documento if trabajador else None
    years = sorted({factor.anio for factor in result.factores_salariales})
    warnings = result.advertencias or ["Revise manualmente la tabla antes de calcular."]

    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(_summary_metric("Trabajador", nombre or "No detectado"), md=3),
                    dbc.Col(_summary_metric("Documento", documento or "No detectado"), md=3),
                    dbc.Col(_summary_metric("Periodos", str(len(result.periodos_certificados))), md=3),
                    dbc.Col(
                        _summary_metric(
                            "Años salariales",
                            ", ".join(str(year) for year in years) if years else "No detectados",
                        ),
                        md=3,
                    ),
                ],
                className="g-3",
            ),
            html.Div(
                [
                    html.H4("Advertencias de extracción", className="cetil-summary__title"),
                    html.Ul([html.Li(warning) for warning in warnings], className="cetil-summary__warnings"),
                ],
                className="cetil-summary__warnings-box",
            ),
        ],
        className="cetil-summary",
    )


def _summary_metric(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="metric-card__label"),
            html.Span(value, className="metric-card__value"),
        ],
        className="metric-card",
    )
