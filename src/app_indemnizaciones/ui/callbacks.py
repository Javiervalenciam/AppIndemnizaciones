from __future__ import annotations

import base64
import binascii

import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from app_indemnizaciones.domain.exceptions import InvalidCetilFileError
from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    ExtractionIssue,
    IssueSeverity,
    cetil_result_from_dict,
    cetil_result_to_dict,
    highest_issue_severity,
)
from app_indemnizaciones.services.cetil_registry import (
    CetilDocumento,
    add_documento,
    content_hash_of_bytes,
    create_documento,
    documentos_from_state,
    documentos_to_state,
    merge_resultados,
    remove_documento,
)
from app_indemnizaciones.services.excel_exporter import (
    build_ipc_export_info,
    build_liquidacion_filename,
    build_liquidacion_xlsx,
)
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
from app_indemnizaciones.ui.diagnostics import (
    build_block_alert,
    build_cetil_diagnostics,
    build_cetil_documents_panel,
    build_documents_status,
    build_pipeline_error_alert,
)
from app_indemnizaciones.ui.state import (
    EMPTY_CETIL_DOCS_STATE,
    EMPTY_CETIL_STATE,
    EMPTY_PERIODOS_STATE,
    EMPTY_RESULTADO_STATE,
)
from app_indemnizaciones.ui.tables import (
    PERIODOS_STYLE_CONDITIONAL,
    build_resultado_metadata,
    build_resultado_table,
    build_totales_row,
)
from app_indemnizaciones.utils.validators import validate_period_rows

# Límite de archivos por carga: evita un callback gigante y da un error claro.
MAX_CETIL_UPLOADS = 10


def register_callbacks(app) -> None:  # noqa: ANN001
    @app.callback(
        Output("ipc-status", "children"),
        Output("ipc-store", "data"),
        Output("ipc-summary-store", "data"),
        Input("upload-ipc", "contents"),
        Input("ipc-summary-store", "modified_timestamp"),
        State("upload-ipc", "filename"),
        State("ipc-summary-store", "data"),
    )
    def sync_ipc_upload(
        contents: str | None,
        _summary_timestamp: int | None,
        filename: str | None,
        stored_summary: dict | None,
    ):
        if ctx.triggered_id == "upload-ipc":
            try:
                ipc_data, summary_data = _parse_ipc_upload(contents, filename)
                return _build_ipc_kpi(summary_data), ipc_data, summary_data
            except Exception as exc:  # UI boundary
                return dbc.Alert(str(exc), color="danger"), no_update, no_update

        if stored_summary:
            return _build_ipc_kpi(stored_summary), no_update, no_update
        return None, no_update, no_update

    @app.callback(
        Output("cetil-docs-store", "data"),
        Output("cetil-docs-list", "children"),
        Output("cetil-store", "data"),
        Output("cetil-upload-status", "children"),
        Output("periodos-import-store", "data", allow_duplicate=True),
        Output("periodos-store", "data", allow_duplicate=True),
        Output("periodos-table", "data", allow_duplicate=True),
        Output("periodos-table", "style_data_conditional", allow_duplicate=True),
        Output("periodos-table", "selected_rows", allow_duplicate=True),
        Output("periodos-alert", "children", allow_duplicate=True),
        Output("resultado-store", "data", allow_duplicate=True),
        Output("resultado-liquidacion", "children", allow_duplicate=True),
        Output("cetil-apply-status", "children", allow_duplicate=True),
        Input("upload-cetil", "contents"),
        State("upload-cetil", "filename"),
        State("cetil-docs-store", "data"),
        prevent_initial_call=True,
    )
    def process_cetil_pdfs(contents, filenames, docs_data):
        documentos = documentos_from_state(docs_data)
        documentos_iniciales = len(documentos)
        cargados = 0
        issues: list[ExtractionIssue] = []
        errores: list[tuple[str | None, Exception]] = []

        try:
            uploads = _iter_uploads(contents, filenames)
        except InvalidCetilFileError as exc:
            return _cetil_outputs(
                documentos,
                build_pipeline_error_alert(exc, code="CETIL_READ_ERROR"),
                invalidate_result=False,
            )

        for payload, filename in uploads:
            try:
                pdf_bytes = _decode_pdf_upload(payload, filename)
                resultado = CetilExtractor().extract_from_bytes(pdf_bytes)
                documento = create_documento(
                    resultado,
                    filename=filename,
                    content_hash=content_hash_of_bytes(pdf_bytes),
                )
                antes = len(documentos)
                documentos, nuevas = add_documento(documentos, documento)
                issues.extend(nuevas)
                if len(documentos) > antes:
                    cargados += 1
            except Exception as exc:  # noqa: BLE001 - se reporta por archivo
                errores.append((filename, exc))

        cambio = len(documentos) != documentos_iniciales

        if errores and cargados == 0:
            first_filename, first_error = errores[0]
            alert = build_pipeline_error_alert(
                first_error,
                code="CETIL_READ_ERROR",
            )
            if first_filename:
                alert.children.insert(0, html.Div(first_filename, className="diagnostics__detail"))
            return _cetil_outputs(documentos, alert, invalidate_result=cambio)

        if not cargados and not errores:
            return _cetil_outputs(
                documentos,
                build_documents_status(documentos, issues),
                invalidate_result=False,
            )

        status = build_documents_status(documentos, issues)
        if errores:
            status.children.append(
                html.Div(
                    "Archivos no procesados: "
                    + ", ".join(name or "sin nombre" for name, _exc in errores)
                    + ".",
                    className="diagnostics__note",
                )
            )
        return _cetil_outputs(documentos, status, invalidate_result=cambio)

    @app.callback(
        Output("cetil-docs-store", "data", allow_duplicate=True),
        Output("cetil-docs-list", "children", allow_duplicate=True),
        Output("cetil-store", "data", allow_duplicate=True),
        Output("cetil-upload-status", "children", allow_duplicate=True),
        Input({"type": "btn-quitar-cetil", "index": ALL}, "n_clicks"),
        State("cetil-docs-store", "data"),
        prevent_initial_call=True,
    )
    def remove_cetil_document(_clicks: list[int | None], docs_data: list[dict] | None):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return no_update, no_update, no_update, no_update
        # Al renderizar la lista, Dash dispara este callback con clics vacíos:
        # solo una acción real del usuario debe quitar un certificado.
        if not any(_clicks or []):
            return no_update, no_update, no_update, no_update

        documentos = remove_documento(
            documentos_from_state(docs_data),
            triggered.get("index"),
        )
        merged = merge_resultados(documentos) if documentos else None
        alert = build_documents_status(
            documentos,
            [],
            note=(
                "Las filas ya agregadas a la tabla no se modificaron. Use "
                "«Agregar periodos CETIL a la tabla» para reconstruirlas desde "
                "los certificados vigentes."
            ),
        )
        return (
            documentos_to_state(documentos),
            build_cetil_documents_panel(documentos),
            cetil_result_to_dict(merged) if merged else None,
            alert,
        )

    @app.callback(
        Output("cetil-docs-store", "data", allow_duplicate=True),
        Output("cetil-docs-list", "children", allow_duplicate=True),
        Output("cetil-store", "data", allow_duplicate=True),
        Output("cetil-upload-status", "children", allow_duplicate=True),
        Output("periodos-import-store", "data", allow_duplicate=True),
        Output("periodos-store", "data", allow_duplicate=True),
        Output("periodos-table", "data", allow_duplicate=True),
        Output("periodos-table", "style_data_conditional", allow_duplicate=True),
        Output("periodos-table", "selected_rows", allow_duplicate=True),
        Output("periodos-alert", "children", allow_duplicate=True),
        Output("resultado-store", "data", allow_duplicate=True),
        Output("resultado-liquidacion", "children", allow_duplicate=True),
        Output("cetil-apply-status", "children", allow_duplicate=True),
        Input("btn-limpiar-cetil", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_cetil_session(n_clicks: int | None):
        return _empty_cetil_ui_outputs()

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
        blocking = [issue for issue in result.issues if issue.is_blocking]
        if blocking:
            return no_update, build_block_alert(blocking)

        rows = cetil_extraction_to_period_rows(result)
        if not rows:
            return no_update, dbc.Alert("No se detectaron periodos certificados para enviar a la tabla.", color="warning")

        return (
            {"rows": rows, "nonce": n_clicks, "replace_fuente": "cetil"},
            _build_apply_status(result, len(rows)),
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
            reemplazar = (import_data.get("replace_fuente") or "").lower()
            if reemplazar:
                # Las filas CETIL se reconstruyen desde los certificados
                # vigentes; las filas manuales se conservan.
                rows = [
                    row
                    for row in rows
                    if (row.get("fuente") or "").lower() != reemplazar
                ]
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
        State("fecha-liquidacion", "date"),
        prevent_initial_call=True,
    )
    def calcular(n_clicks, ipc_data, periodos_data, fecha_liquidacion):
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

            resultado = LiquidacionService(repo).calcular(
                periodos,
                fecha_liquidacion=fecha_liquidacion,
            )
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
                    build_resultado_metadata(resultado),
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
        except Exception as exc:  # noqa: BLE001 - se reporta con código de cálculo
            return (
                build_pipeline_error_alert(exc, code="CALCULO_UNEXPECTED_ERROR"),
                no_update,
            )

    @app.callback(
        Output("download-liquidacion", "data"),
        Input("btn-download", "n_clicks"),
        State("resultado-store", "data"),
        State("ipc-store", "data"),
        State("cetil-store", "data"),
        prevent_initial_call=True,
    )
    def descargar_excel(n_clicks, resultado_data, ipc_data, cetil_data):
        if not resultado_data:
            return no_update
        resultado = resultado_from_dict(resultado_data)
        repo = IpcRepository.from_dataframe(pd.DataFrame(ipc_data)) if ipc_data else None
        cetil_result = cetil_result_from_dict(cetil_data) if cetil_data else None
        xlsx = build_liquidacion_xlsx(
            resultado,
            cetil_result=cetil_result,
            ipc_info=(
                build_ipc_export_info(repo, fecha_liquidacion=resultado.fecha_liquidacion)
                if repo
                else None
            ),
        )
        return dcc.send_bytes(xlsx, build_liquidacion_filename(cetil_result))


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


def _cetil_outputs(
    documentos: list[CetilDocumento],
    alert: object,
    *,
    invalidate_result: bool = True,
) -> tuple:
    """Salidas del callback de carga de certificados.

    La tabla y la liquidación solo se invalidan cuando el conjunto de
    certificados cambió; un archivo duplicado o ilegible no debe borrar un
    cálculo vigente.
    """
    merged = merge_resultados(documentos) if documentos else None
    resultado_store = EMPTY_RESULTADO_STATE if invalidate_result else no_update
    resultado_vista = None if invalidate_result else no_update
    return (
        documentos_to_state(documentos),
        build_cetil_documents_panel(documentos),
        cetil_result_to_dict(merged) if merged else None,
        alert,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        resultado_store,
        resultado_vista,
        no_update,
    )


def _iter_uploads(
    contents: object,
    filenames: object,
) -> list[tuple[str | None, str | None]]:
    """Normaliza la carga de `dcc.Upload` con `multiple=True` o `False`."""
    if isinstance(contents, (list, tuple)):
        names = (
            list(filenames)
            if isinstance(filenames, (list, tuple))
            else [filenames] * len(contents)
        )
        uploads = list(zip(contents, names, strict=False))
    else:
        uploads = [(contents, filenames)]
    limited = uploads[:MAX_CETIL_UPLOADS]
    if len(uploads) > MAX_CETIL_UPLOADS:
        raise InvalidCetilFileError(
            f"Se cargaron {len(uploads)} archivos CETIL a la vez; el máximo es "
            f"{MAX_CETIL_UPLOADS}. Cárguelos en varios intentos."
        )
    return [(str(payload) if payload is not None else None, _text_or_none(name)) for payload, name in limited]


def _text_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _build_apply_status(result: CetilExtractionResult, row_count: int) -> dbc.Alert:
    highest = highest_issue_severity(result.issues)
    requiere_revision = highest is not None and highest.rank >= IssueSeverity.REVIEW_REQUIRED.rank
    color = "warning" if requiere_revision else "info"
    detail = ""
    if result.issues:
        detail = (
            f" El diagnóstico registra {len(result.issues)} incidencia(s); "
            "revíselas en el paso 3 antes de calcular."
        )
    return dbc.Alert(
        f"Se reconstruyeron {row_count} fila(s) anualizada(s) desde los "
        "certificados CETIL cargados (las filas CETIL previas se reemplazaron; "
        f"las manuales se conservan). Revise IBL y errores antes de calcular.{detail}",
        color=color,
    )


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


def _parse_ipc_upload(
    contents: str | None,
    filename: str | None,
) -> tuple[list[dict[str, str]], dict[str, str | int]]:
    repo = IpcRepository.from_upload_contents(contents or "", filename or "")
    summary = repo.summary()
    ipc_data = [
        {"periodo": row.periodo, "fecha": row.fecha.isoformat(), "indice": str(row.indice)}
        for row in repo.registros
    ]
    summary_data = {
        "filename": filename or "archivo IPC",
        "total_registros": summary.total_registros,
        "periodo_minimo": summary.periodo_minimo,
        "periodo_maximo": summary.periodo_maximo,
        "ipc_actual": str(summary.ipc_actual),
    }
    return ipc_data, summary_data


def _build_ipc_kpi(summary_data: dict) -> html.Div:
    total_registros = summary_data.get("total_registros", 0)
    periodo_minimo = summary_data.get("periodo_minimo", "N/D")
    periodo_maximo = summary_data.get("periodo_maximo", "N/D")
    ipc_actual = summary_data.get("ipc_actual", "N/D")
    filename = summary_data.get("filename", "archivo IPC")

    return html.Div(
        [
            html.Div(
                [
                    html.Span("Historico validado", className="ipc-kpi__eyebrow"),
                    html.Span(f"{total_registros} registros", className="ipc-kpi__pill"),
                ],
                className="ipc-kpi__header",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Ultimo IPC", className="ipc-kpi__label"),
                            html.Strong(periodo_maximo, className="ipc-kpi__value"),
                        ],
                        className="ipc-kpi__metric",
                    ),
                    html.Div(
                        [
                            html.Span("IPC actual", className="ipc-kpi__label"),
                            html.Strong(ipc_actual, className="ipc-kpi__value"),
                        ],
                        className="ipc-kpi__metric ipc-kpi__metric--accent",
                    ),
                ],
                className="ipc-kpi__grid",
            ),
            html.Div(
                f"Rango {periodo_minimo} a {periodo_maximo}. Fuente: {filename}.",
                className="ipc-kpi__meta",
            ),
        ],
        className="ipc-kpi",
    )


def _empty_cetil_ui_outputs() -> tuple:
    return (
        list(EMPTY_CETIL_DOCS_STATE),
        build_cetil_documents_panel([]),
        EMPTY_CETIL_STATE,
        None,
        None,
        list(EMPTY_PERIODOS_STATE),
        list(EMPTY_PERIODOS_STATE),
        PERIODOS_STYLE_CONDITIONAL,
        [],
        None,
        EMPTY_RESULTADO_STATE,
        None,
        None,
    )


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
    metadata = result.metadata
    trabajador = result.trabajador
    entidad = result.entidad_empleadora
    nombre = trabajador.nombre_completo if trabajador else None
    tipo_documento = trabajador.tipo_documento if trabajador else None
    documento = trabajador.documento if trabajador else None
    fecha_nacimiento = trabajador.fecha_nacimiento.isoformat() if trabajador and trabajador.fecha_nacimiento else None
    genero = trabajador.genero if trabajador and trabajador.genero else "No detectado"
    nombre_entidad = entidad.nombre_entidad_empleadora if entidad else None
    nit_entidad = entidad.nit_entidad_empleadora if entidad else None
    fecha_vigencia = (
        entidad.fecha_vigencia_sistema_general_pensiones.isoformat()
        if entidad and entidad.fecha_vigencia_sistema_general_pensiones
        else None
    )
    years = sorted({factor.anio for factor in result.factores_salariales})

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Trabajador", className="cetil-profile__label"),
                            html.H3(nombre or "No detectado", className="cetil-profile__name"),
                            html.Div(
                                [
                                    html.Span(f"{tipo_documento or 'No detectado'} {documento or ''}".strip()),
                                    html.Span(fecha_nacimiento or "Fecha nacimiento no detectada"),
                                    html.Span(f"Género: {genero}"),
                                ],
                                className="cetil-profile__meta",
                            ),
                        ],
                        className="cetil-profile",
                    ),
                    html.Div(
                        [
                            _summary_metric(
                                "CETIL principal",
                                metadata.numero_cetil if metadata else "No detectado",
                            ),
                            _summary_metric(
                                "Fecha CETIL",
                                metadata.fecha_expedicion_cetil.isoformat()
                                if metadata and metadata.fecha_expedicion_cetil
                                else "No detectada",
                            ),
                            _summary_metric(
                                "Ciudad CETIL",
                                metadata.ciudad_expedicion
                                if metadata and metadata.ciudad_expedicion
                                else "No detectada",
                            ),
                        ],
                        className="cetil-summary-card",
                    ),
                    html.Div(
                        [
                            _summary_metric("Entidad empleadora", nombre_entidad or "No detectada"),
                            _summary_metric("NIT", nit_entidad or "No detectado"),
                            _summary_metric("Vigencia pensional", fecha_vigencia or "No detectada"),
                        ],
                        className="cetil-summary-card",
                    ),
                    html.Div(
                        [
                            _summary_metric("Periodos", str(len(result.periodos_certificados))),
                            _summary_metric("Filas anuales", str(len(result.filas_liquidables_anuales))),
                            _summary_metric(
                                "Años salariales",
                                ", ".join(str(year) for year in years) if years else "No detectados",
                            ),
                            _summary_metric("Incidencias", str(len(result.issues))),
                        ],
                        className="cetil-summary-card",
                    ),
                ],
                className="cetil-summary-grid",
            ),
            build_cetil_diagnostics(result),
        ],
        className="cetil-summary",
    )


def _summary_metric(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="metric-card__label"),
            html.Span(value, className="metric-card__value"),
        ],
        className="metric-card metric-card--compact",
    )
