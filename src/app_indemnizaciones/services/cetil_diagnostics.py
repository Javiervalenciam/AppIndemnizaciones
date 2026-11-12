"""Diagnóstico legible de una extracción CETIL.

Esta capa NO extrae ni calcula: toma el `CetilExtractionResult` ya construido y
lo traduce a datos presentables (campo, estado, valor, página e incidencias).
La UI solo renderiza; toda decisión de estado vive aquí.
"""

from __future__ import annotations

from dataclasses import dataclass

from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    ExtractionIssue,
    IssueSeverity,
    count_issues_by_severity,
    highest_issue_severity,
)

STATUS_OK = "OK"
STATUS_WARNING = "REVISAR"
STATUS_MISSING = "FALTANTE"
STATUS_BLOCKED = "BLOQUEADO"


@dataclass(frozen=True)
class FieldDiagnostic:
    field: str
    label: str
    status: str
    value: str
    page: str
    note: str = ""


@dataclass(frozen=True)
class ExtractionSummary:
    total_issues: int
    counts: dict[str, int]
    highest_severity: IssueSeverity | None
    blocking_issues: tuple[ExtractionIssue, ...]
    status_color: str
    status_title: str
    status_message: str


def build_field_diagnostics(result: CetilExtractionResult) -> list[FieldDiagnostic]:
    metadata = result.metadata
    trabajador = result.trabajador
    entidad = result.entidad_empleadora
    pages = result.texto_paginas
    header_page = _page_label(pages, "CERTIFICACIÓN ELECTRÓNICA") or "1"
    employee_page = _page_label(pages, "DATOS DEL EMPLEADO") or header_page
    entity_page = _page_label(pages, "DATOS DE LA ENTIDAD EMPLEADORA") or header_page
    periods_page = _page_label(pages, "PERIODOS CERTIFICADOS")
    salary_page = _page_label(pages, "FACTORES SALARIALES")

    declared_days = sum(
        periodo.dias_interrupcion or 0
        for periodo in result.periodos_certificados
        if periodo.dias_interrupcion is not None
    )
    labor_days = sum(
        (periodo.fecha_hasta - periodo.fecha_desde).days + 1
        for periodo in result.periodos_certificados
        if periodo.fecha_desde is not None and periodo.fecha_hasta is not None
    )
    salary_years = sorted({factor.anio for factor in result.factores_salariales})
    annual_years = [row.anio for row in result.filas_liquidables_anuales]
    years_without_ibl = [
        str(row.anio) for row in result.filas_liquidables_anuales if row.ibl_reportado is None
    ]
    years_pending_ibl = [
        str(row.anio) for row in result.filas_liquidables_anuales if row.ibl_requiere_revision
    ]
    ibl_methods = sorted(
        {
            row.ibl_metodo
            for row in result.filas_liquidables_anuales
            if row.ibl_metodo and row.ibl_metodo != "manual"
        }
    )

    return [
        FieldDiagnostic(
            field="metadata.numero_cetil",
            label="Número CETIL",
            **_status(metadata.numero_cetil if metadata else None),
            value=metadata.numero_cetil if metadata and metadata.numero_cetil else "",
            page=header_page,
        ),
        FieldDiagnostic(
            field="metadata.fecha_expedicion_cetil",
            label="Ciudad y fecha de expedición",
            **_status(_expedition_text(result)),
            value=_expedition_text(result) or "",
            page=header_page,
        ),
        FieldDiagnostic(
            field="trabajador.nombre_completo",
            label="Trabajador",
            **_status(trabajador.nombre_completo if trabajador else None),
            value=trabajador.nombre_completo if trabajador and trabajador.nombre_completo else "",
            page=employee_page,
        ),
        FieldDiagnostic(
            field="trabajador.documento",
            label="Documento",
            **_status(trabajador.documento if trabajador else None),
            value=_document_text(trabajador),
            page=employee_page,
        ),
        FieldDiagnostic(
            field="trabajador.fecha_nacimiento",
            label="Fecha de nacimiento",
            **_status(trabajador.fecha_nacimiento if trabajador else None),
            value=trabajador.fecha_nacimiento.isoformat()
            if trabajador and trabajador.fecha_nacimiento
            else "",
            page=employee_page,
        ),
        FieldDiagnostic(
            field="trabajador.genero",
            label="Género",
            **_status(trabajador.genero if trabajador else None),
            value=trabajador.genero if trabajador and trabajador.genero else "",
            page=employee_page,
            note=_genero_note(trabajador),
        ),
        FieldDiagnostic(
            field="entidad_empleadora.nombre",
            label="Entidad empleadora",
            **_status(entidad.nombre_entidad_empleadora if entidad else None),
            value=entidad.nombre_entidad_empleadora
            if entidad and entidad.nombre_entidad_empleadora
            else "",
            page=entity_page,
        ),
        FieldDiagnostic(
            field="entidad_empleadora.nit",
            label="NIT entidad empleadora",
            **_status(entidad.nit_entidad_empleadora if entidad else None),
            value=entidad.nit_entidad_empleadora
            if entidad and entidad.nit_entidad_empleadora
            else "",
            page=entity_page,
        ),
        FieldDiagnostic(
            field="entidad_empleadora.vigencia",
            label="Vigencia pensional",
            **_status(
                entidad.fecha_vigencia_sistema_general_pensiones if entidad else None
            ),
            value=entidad.fecha_vigencia_sistema_general_pensiones.isoformat()
            if entidad and entidad.fecha_vigencia_sistema_general_pensiones
            else "",
            page=entity_page,
        ),
        FieldDiagnostic(
            field="entidad_certificadora",
            label="Entidad certificadora",
            **_status(result.entidad_certificadora),
            value=result.entidad_certificadora or "",
            page=header_page,
        ),
        FieldDiagnostic(
            field="periodos_certificados",
            label="Periodos certificados",
            status=STATUS_OK if result.periodos_certificados else STATUS_MISSING,
            value=(
                f"{len(result.periodos_certificados)} vinculación(es); "
                f"{labor_days} día(s) laborados; "
                f"{declared_days} día(s) de interrupción declarados"
                if result.periodos_certificados
                else ""
            ),
            page=periods_page or "",
            note="Los días de interrupción no son días laborados.",
        ),
        FieldDiagnostic(
            field="factores_salariales",
            label="Factores salariales",
            status=STATUS_OK if result.factores_salariales else STATUS_MISSING,
            value=(
                f"{len(result.factores_salariales)} registro(s); años "
                f"{_years_text(salary_years)}"
                if result.factores_salariales
                else ""
            ),
            page=salary_page or "",
        ),
        FieldDiagnostic(
            field="filas_liquidables_anuales",
            label="Filas anuales para liquidar",
            status=STATUS_WARNING if years_without_ibl else (
                STATUS_OK if result.filas_liquidables_anuales else STATUS_MISSING
            ),
            value=(
                f"{len(result.filas_liquidables_anuales)} fila(s); años "
                f"{_years_text(annual_years)}"
                if result.filas_liquidables_anuales
                else ""
            ),
            page="",
            note=(
                f"Sin IBL: {', '.join(years_without_ibl)}. "
                if years_without_ibl
                else "Todas las filas tienen IBL sugerido. "
            )
            + (
                f"Revisar IBL: {', '.join(years_pending_ibl)}. "
                if years_pending_ibl
                else ""
            )
            + (
                f"Método: {', '.join(ibl_methods)}."
                if ibl_methods
                else ""
            ),
        ),
        FieldDiagnostic(
            field="documento.paginas",
            label="Páginas del PDF",
            status=STATUS_OK if result.texto_paginas else STATUS_BLOCKED,
            value=str(len(result.texto_paginas)),
            page="",
        ),
    ]


def build_extraction_summary(result: CetilExtractionResult) -> ExtractionSummary:
    issues = result.issues
    counts = count_issues_by_severity(issues)
    highest = highest_issue_severity(issues)
    blocking = tuple(issue for issue in issues if issue.is_blocking)

    if highest is IssueSeverity.BLOCK:
        title = "Extracción bloqueada"
        message = (
            "El documento no puede procesarse. Corrija la causa indicada antes de intentar "
            "agregar periodos o calcular."
        )
        color = "danger"
    elif highest is IssueSeverity.ERROR:
        title = "Extracción con errores"
        message = (
            f"Se detectaron {counts[IssueSeverity.ERROR.value]} error(es). "
            "Revise las incidencias antes de calcular."
        )
        color = "danger"
    elif highest is IssueSeverity.REVIEW_REQUIRED:
        title = "Extracción con datos por revisar"
        message = (
            f"Se detectaron {counts[IssueSeverity.REVIEW_REQUIRED.value]} dato(s) que requieren "
            "confirmación manual antes de calcular."
        )
        color = "warning"
    elif highest is IssueSeverity.WARNING:
        title = "Extracción con advertencias"
        message = (
            f"Se detectaron {counts[IssueSeverity.WARNING.value]} advertencia(s) no bloqueantes. "
            "Puede revisar y continuar."
        )
        color = "warning"
    elif highest is IssueSeverity.INFO:
        title = "Extracción completada"
        message = (
            f"Se registraron {counts[IssueSeverity.INFO.value]} nota(s) informativas; "
            "no requieren acción."
        )
        color = "info"
    else:
        title = "Extracción completada"
        message = "No se registraron incidencias en la extracción."
        color = "success"

    return ExtractionSummary(
        total_issues=len(issues),
        counts=counts,
        highest_severity=highest,
        blocking_issues=blocking,
        status_color=color,
        status_title=title,
        status_message=message,
    )


def _genero_note(trabajador: object) -> str:
    """Nota informativa del género; nunca es una alarma (no afecta el cálculo)."""
    if trabajador is None or not getattr(trabajador, "genero", None):
        return "No consta en el CETIL ni en la base de nombres; opcional, no afecta el cálculo."
    if getattr(trabajador, "genero_origen", None) == "base_nombres":
        return "Inferido por el nombre (base de nombres); verifique. No afecta el cálculo."
    return "Opcional para el cálculo; se reporta para el expediente."


def _status(value: object) -> dict[str, str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return {"status": STATUS_MISSING}
    return {"status": STATUS_OK}


def _expedition_text(result: CetilExtractionResult) -> str | None:
    metadata = result.metadata
    if metadata is None:
        return None
    ciudad = metadata.ciudad_expedicion or ""
    fecha = metadata.fecha_expedicion_cetil.isoformat() if metadata.fecha_expedicion_cetil else ""
    text = ", ".join(part for part in (ciudad, fecha) if part)
    return text or None


def _document_text(trabajador: object) -> str:
    tipo = getattr(trabajador, "tipo_documento", None)
    numero = getattr(trabajador, "documento", None)
    return " ".join(part for part in (tipo, numero) if part)


def _years_text(years: list[int]) -> str:
    if not years:
        return "sin años detectados"
    ordered = sorted(set(years))
    if len(ordered) <= 6:
        return ", ".join(str(year) for year in ordered)
    return f"{ordered[0]}–{ordered[-1]}"


def _page_label(pages: dict[int, str], needle: str) -> str | None:
    normalized_needle = _normalize(needle)
    for page_number in sorted(pages):
        if normalized_needle in _normalize(pages[page_number]):
            return str(page_number)
    return None


def _normalize(text: str) -> str:
    return " ".join((text or "").upper().split())
