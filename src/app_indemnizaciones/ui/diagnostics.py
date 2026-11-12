"""Panel de diagnóstico de extracción CETIL.

Solo presentación: recibe datos ya calculados por
`app_indemnizaciones.services.cetil_diagnostics` y devuelve nodos Dash.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from app_indemnizaciones.domain.exceptions import AppIndemnizacionesError
from app_indemnizaciones.services.cetil_diagnostics import (
    STATUS_BLOCKED,
    STATUS_MISSING,
    STATUS_OK,
    STATUS_WARNING,
    FieldDiagnostic,
    build_extraction_summary,
    build_field_diagnostics,
)
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    ExtractionIssue,
    IssueSeverity,
    count_issues_by_severity,
    highest_issue_severity,
)
from app_indemnizaciones.services.cetil_registry import CetilDocumento

_SEVERITY_CLASS = {
    IssueSeverity.INFO: "diagnostic-badge--info",
    IssueSeverity.WARNING: "diagnostic-badge--warning",
    IssueSeverity.REVIEW_REQUIRED: "diagnostic-badge--review",
    IssueSeverity.ERROR: "diagnostic-badge--error",
    IssueSeverity.BLOCK: "diagnostic-badge--block",
}

_FIELD_CLASS = {
    STATUS_OK: "diagnostic-field--ok",
    STATUS_WARNING: "diagnostic-field--warning",
    STATUS_MISSING: "diagnostic-field--missing",
    STATUS_BLOCKED: "diagnostic-field--block",
}


def build_extraction_status_alert(
    result: CetilExtractionResult,
    filename: str | None = None,
) -> dbc.Alert:
    """Alerta del paso 2: dice qué pasó y cuántas incidencias hay."""
    summary = build_extraction_summary(result)
    name = filename or "archivo PDF"
    counts = " · ".join(
        f"{severity.label}: {summary.counts[severity.value]}"
        for severity in reversed(list(IssueSeverity))
        if summary.counts[severity.value]
    )
    children: list[object] = [
        html.Strong(f"{summary.status_title}: {name}."),
        html.Div(summary.status_message),
    ]
    if counts:
        children.append(html.Div(counts, className="diagnostics__counts"))
    children.append(
        html.Div(
            "El detalle está en «Diagnóstico de extracción» (paso 3).",
            className="diagnostics__hint",
        )
    )
    return dbc.Alert(children, color=summary.status_color, className="mb-0")


def build_block_alert(issues: list[ExtractionIssue] | tuple[ExtractionIssue, ...]) -> dbc.Alert:
    items = [
        html.Li(
            [
                html.Span(issue.code.value, className="diagnostic-code"),
                html.Span(f" — {issue.message}"),
                html.Span(f" {issue.action}" if issue.action else ""),
            ]
        )
        for issue in issues
    ]
    return dbc.Alert(
        [
            html.Strong("No se puede continuar: el documento tiene incidencias bloqueantes."),
            html.Ul(items, className="mb-0"),
        ],
        color="danger",
        className="mb-0",
    )


def build_pipeline_error_alert(
    exc: Exception,
    *,
    code: str = "CETIL_UNEXPECTED_ERROR",
) -> dbc.Alert:
    """Convierte una excepción en un mensaje con código y acción."""
    if isinstance(exc, AppIndemnizacionesError):
        title = "No se pudo procesar el CETIL"
        detail = str(exc)
        action = "Corrija la causa indicada y vuelva a cargar el archivo."
    else:
        title = "Error inesperado durante el procesamiento"
        detail = f"{type(exc).__name__}: {exc}"
        action = (
            "Este es un defecto del motor, no de sus datos. "
            "Reporte el código y el archivo que lo produjo."
        )
    return dbc.Alert(
        [
            html.Strong(f"{title} ({code})."),
            html.Div(detail, className="diagnostics__detail"),
            html.Div(action, className="diagnostics__hint"),
        ],
        color="danger",
        className="mb-0",
    )


def build_cetil_documents_panel(documentos: list[CetilDocumento]) -> html.Div:
    """Lista los certificados cargados con su procedencia y acción de quitar."""
    if not documentos:
        return html.Div(
            "Aún no hay certificados cargados.",
            className="cetil-docs__empty",
        )
    items = []
    for documento in documentos:
        items.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(documento.etiqueta, className="cetil-docs__label"),
                            html.Span(
                                f"{documento.periodos_anuales} fila(s) anual(es) · "
                                f"{len(documento.resultado.issues)} incidencia(s)",
                                className="diagnostics__note",
                            ),
                        ],
                        className="cetil-docs__info",
                    ),
                    dbc.Button(
                        "Quitar",
                        id={"type": "btn-quitar-cetil", "index": documento.documento_id},
                        color="link",
                        size="sm",
                        className="cetil-docs__remove",
                    ),
                ],
                className="cetil-docs__item",
            )
        )
    return html.Div(
        [
            html.H5(
                f"Certificados cargados ({len(documentos)})",
                className="diagnostics__section-title",
            ),
            *items,
        ],
        className="cetil-docs",
    )


def build_documents_status(
    documentos: list[CetilDocumento],
    issues: list[ExtractionIssue] | tuple[ExtractionIssue, ...],
    *,
    note: str | None = None,
) -> dbc.Alert:
    """Resume el resultado de cargar o quitar certificados en la sesión."""
    highest = highest_issue_severity(list(issues))
    if highest in {IssueSeverity.BLOCK, IssueSeverity.ERROR}:
        color = "danger"
    elif highest is IssueSeverity.REVIEW_REQUIRED:
        color = "warning"
    else:
        color = "info"

    children: list[object] = [
        html.Strong(
            f"Sesión CETIL: {len(documentos)} certificado(s) cargado(s)."
        )
    ]
    if not documentos:
        children.append(
            html.Div(
                "No quedan certificados. Cargue al menos uno para calcular.",
                className="diagnostics__note",
            )
        )
    attention = [
        issue for issue in issues if issue.severity.rank >= IssueSeverity.WARNING.rank
    ]
    if attention:
        children.append(
            html.Ul(
                [
                    html.Li(
                        [
                            html.Span(issue.code.value, className="diagnostic-code"),
                            html.Span(f" — {issue.message}"),
                        ]
                    )
                    for issue in attention
                ],
                className="mb-0",
            )
        )
    if note:
        children.append(html.Div(note, className="diagnostics__note"))
    return dbc.Alert(children, color=color, className="mb-0")


def build_cetil_diagnostics(result: CetilExtractionResult) -> html.Div:
    summary = build_extraction_summary(result)
    fields = build_field_diagnostics(result)
    attention = _sorted_issues(
        [i for i in result.issues if i.severity.rank >= IssueSeverity.WARNING.rank]
    )
    info = _sorted_issues(
        [i for i in result.issues if i.severity.rank < IssueSeverity.WARNING.rank]
    )
    children: list[object] = [
        html.Div(
            [
                html.H4("Diagnóstico de extracción", className="diagnostics__title"),
                html.P(summary.status_message, className="diagnostics__subtitle"),
            ],
            className="diagnostics__header",
        ),
        _severity_counters(result),
    ]
    if attention:
        children.append(_attention_section(attention))
    else:
        children.append(
            html.Div(
                "No se registraron incidencias en la extracción."
                if not result.issues
                else "Sin incidencias que requieran acción.",
                className="diagnostics__empty",
            )
        )
    if info:
        children.append(_info_section(info))
    children.append(_fields_section(fields))
    return html.Div(children, className="cetil-diagnostics")


def _sorted_issues(issues: list[ExtractionIssue]) -> list[ExtractionIssue]:
    return sorted(
        issues,
        key=lambda issue: (-issue.severity.rank, issue.page or 0, issue.field or ""),
    )


def _severity_counters(result: CetilExtractionResult) -> html.Div:
    counts = count_issues_by_severity(result.issues)
    total = len(result.issues)
    pills = [
        html.Span(
            [
                html.Span(severity.label, className="diagnostics__pill-label"),
                html.Strong(str(counts[severity.value]), className="diagnostics__pill-value"),
            ],
            className=(
                "diagnostics__pill "
                + _SEVERITY_CLASS[severity].replace("diagnostic-badge--", "diagnostics__pill--")
            ),
        )
        for severity in reversed(list(IssueSeverity))
        if counts[severity.value]
    ]
    if not pills:
        pills = [html.Span("Sin incidencias", className="diagnostics__pill diagnostics__pill--ok")]
    return html.Div(
        [
            html.Span(f"{total} incidencia(s)", className="diagnostics__total"),
            *pills,
        ],
        className="diagnostics__pills",
    )


def _fields_section(rows: list[FieldDiagnostic]) -> html.Div:
    problems = [row for row in rows if row.status != STATUS_OK]
    detected = len(rows) - len(problems)
    children: list[object] = []
    if problems:
        children.append(
            html.Div(
                [
                    html.Span("Campos por revisar:", className="diagnostics__note"),
                    *[
                        html.Span(
                            f"{row.label} · {row.status}",
                            className="diagnostic-status " + _FIELD_CLASS.get(row.status, ""),
                        )
                        for row in problems
                    ],
                ],
                className="diagnostics__chips",
            )
        )
    children.append(
        html.Details(
            [
                html.Summary(f"Ver campos detectados ({detected} de {len(rows)})"),
                html.Div(
                    html.Table(
                        [
                            html.Thead(
                                html.Tr(
                                    [html.Th("Campo"), html.Th("Estado"), html.Th("Valor")]
                                )
                            ),
                            html.Tbody([_field_row(row) for row in rows]),
                        ],
                        className="diagnostics__table",
                    ),
                    className="diagnostics__table-wrap",
                ),
            ],
            className="diagnostics__details",
        )
    )
    return html.Div(children, className="diagnostics__block")


def _field_row(row: FieldDiagnostic) -> html.Tr:
    page = f" · pág. {row.page}" if row.page and row.page != "—" else ""
    return html.Tr(
        [
            html.Td(row.label),
            html.Td(
                html.Span(
                    row.status,
                    className="diagnostic-status " + _FIELD_CLASS.get(row.status, ""),
                )
            ),
            html.Td(
                [
                    html.Span(row.value or "No detectado"),
                    html.Span(
                        f" {row.note}{page}" if row.note else page,
                        className="diagnostics__note",
                    ),
                ],
                className="diagnostics__cell-value",
            ),
        ]
    )


def _attention_section(issues: list[ExtractionIssue]) -> html.Div:
    return html.Div(
        [
            html.H5(
                f"Requiere atención ({len(issues)})",
                className="diagnostics__section-title",
            ),
            html.Ul(
                [_issue_card(issue) for issue in issues],
                className="diagnostics__issues",
            ),
        ],
        className="diagnostics__block",
    )


def _info_section(issues: list[ExtractionIssue]) -> html.Details:
    return html.Details(
        [
            html.Summary(f"Ver notas informativas ({len(issues)})"),
            html.Ul(
                [_issue_card(issue) for issue in issues],
                className="diagnostics__issues",
            ),
        ],
        className="diagnostics__details",
    )


def _issue_card(issue: ExtractionIssue) -> html.Li:
    location = issue.field or "documento"
    if issue.page:
        location = f"{location} · pág. {issue.page}"
    head = html.Div(
        [
            html.Span(
                f"{issue.severity.label} · {issue.code.value}",
                className=f"diagnostic-badge {_SEVERITY_CLASS[issue.severity]}",
            ),
            html.Span(issue.message, className="diagnostics__issue-msg", title=issue.message),
            html.Span(location, className="diagnostics__note diagnostics__issue-loc"),
        ],
        className="diagnostics__issue-head",
    )
    body: list[object] = [head]
    if issue.action:
        body.append(
            html.Div(
                [html.Strong("Qué hacer: "), issue.action],
                className="diagnostics__issue-action",
                title=issue.action,
            )
        )
    if issue.cause:
        body.append(
            html.Details(
                [html.Summary("Detalle"), html.Div(issue.cause, className="diagnostics__note")],
                className="diagnostics__issue-detail",
            )
        )
    return html.Li(body, className="diagnostics__issue")
