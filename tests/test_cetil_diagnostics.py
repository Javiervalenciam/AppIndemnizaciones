from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app_indemnizaciones.services.cetil_diagnostics import (
    STATUS_MISSING,
    build_extraction_summary,
    build_field_diagnostics,
)
from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    CetilPeriodoCertificado,
    ExtractionIssue,
    ExtractionIssueCode,
    IssueSeverity,
    cetil_result_from_dict,
    cetil_result_to_dict,
)


def _empty_result() -> CetilExtractionResult:
    return CetilExtractor().extract_from_pages({1: "   ", 2: ""})


def test_pdf_sin_capa_de_texto_bloquea_con_resultado_vacio():
    result = _empty_result()

    assert [issue.code for issue in result.issues] == [ExtractionIssueCode.PDF_NO_TEXT_LAYER]
    assert result.issues[0].severity is IssueSeverity.BLOCK
    assert result.confidence_score == 0.0
    assert result.periodos_certificados == []
    assert result.factores_salariales == []
    assert result.advertencias


def test_pagina_sin_texto_pero_documento_con_texto_solo_advertencia():
    result = CetilExtractor().extract_from_pages(
        {1: "CERTIFICACIÓN ELECTRÓNICA DE TIEMPOS LABORADOS", 2: ""}
    )

    severities = {issue.code: issue.severity for issue in result.issues}
    assert ExtractionIssueCode.PDF_PAGE_WITHOUT_TEXT in severities
    assert never_blocking(result)


def never_blocking(result: CetilExtractionResult) -> bool:
    return not any(issue.severity is IssueSeverity.BLOCK for issue in result.issues)


def test_issues_sobreviven_serializacion_y_deserializacion():
    result = CetilExtractor().extract_from_pages(
        {1: "CERTIFICACIÓN ELECTRÓNICA DE TIEMPOS LABORADOS"}
    )
    payload = cetil_result_to_dict(result)
    restored = cetil_result_from_dict(payload)

    assert [issue.code for issue in restored.issues] == [issue.code for issue in result.issues]
    assert [issue.severity for issue in restored.issues] == [
        issue.severity for issue in result.issues
    ]
    assert [issue.message for issue in restored.issues] == [
        issue.message for issue in result.issues
    ]


def test_issue_desconocida_no_rompe_deserializacion():
    payload = {
        "issues": [
            {
                "code": "CODIGO_QUE_YA_NO_EXISTE",
                "severity": "REVIEW_REQUIRED",
                "message": "Incidencia antigua.",
            }
        ]
    }
    restored = cetil_result_from_dict(payload)

    assert restored.issues[0].severity is IssueSeverity.REVIEW_REQUIRED
    assert restored.issues[0].code is ExtractionIssueCode.PDF_UNREADABLE


def test_resumen_reporta_bloqueo_y_detiene_el_flujo():
    summary = build_extraction_summary(_empty_result())

    assert summary.status_color == "danger"
    assert summary.status_title == "Extracción bloqueada"
    assert summary.highest_severity is IssueSeverity.BLOCK
    assert summary.blocking_issues


def test_resumen_ordena_la_severidad_mas_alta():
    result = replace(
        _empty_result(),
        issues=[
            ExtractionIssue(
                code=ExtractionIssueCode.METADATA_MISSING,
                severity=IssueSeverity.WARNING,
                message="Sin número CETIL.",
            ),
            ExtractionIssue(
                code=ExtractionIssueCode.IBL_MANUAL_REQUIRED,
                severity=IssueSeverity.REVIEW_REQUIRED,
                message="Falta IBL 1984.",
            ),
        ],
    )
    summary = build_extraction_summary(result)

    assert summary.highest_severity is IssueSeverity.REVIEW_REQUIRED
    assert summary.counts["WARNING"] == 1
    assert summary.counts["REVIEW_REQUIRED"] == 1
    assert summary.total_issues == 2


def test_resumen_sin_incidencias_es_exitoso():
    result = CetilExtractionResult()
    summary = build_extraction_summary(result)

    assert summary.highest_severity is None
    assert summary.status_color == "success"
    assert summary.total_issues == 0


def test_diagnostico_separa_dias_laborados_de_dias_de_interrupcion():
    result = CetilExtractionResult(
        periodos_certificados=[
            CetilPeriodoCertificado(
                fecha_desde=date(1984, 12, 30),
                fecha_hasta=date(1984, 12, 31),
                dias_interrupcion=5,
                total_no_dias=5,
            )
        ]
    )
    row = _row(result, "periodos_certificados")

    assert "2 día(s) laborados" in row.value
    assert "5 día(s) de interrupción declarados" in row.value


def test_diagnostico_marca_campo_faltante():
    row = _row(_empty_result(), "trabajador.documento")

    assert row.status == STATUS_MISSING
    assert row.value == ""


def test_trabajador_no_recuperado_muestra_documento_vacio():
    result = CetilExtractionResult(trabajador=None)
    row = _row(result, "trabajador.documento")

    assert row.value == ""
    assert row.status == STATUS_MISSING


def test_filas_anuales_sin_ibl_se_marcan_para_revision():
    from app_indemnizaciones.services.cetil_models import PeriodoLiquidableAnual

    result = CetilExtractionResult(
        filas_liquidables_anuales=[
            PeriodoLiquidableAnual(
                anio=1984,
                fecha_inicio=date(1984, 1, 1),
                fecha_fin=date(1984, 12, 31),
                ibl_reportado=None,
            ),
            PeriodoLiquidableAnual(
                anio=1985,
                fecha_inicio=date(1985, 1, 1),
                fecha_fin=date(1985, 12, 31),
                ibl_reportado=Decimal("12427.00"),
            ),
        ]
    )
    row = _row(result, "filas_liquidables_anuales")

    assert row.status == "REVISAR"
    assert "1984" in row.note


def _row(result: CetilExtractionResult, field: str):
    for row in build_field_diagnostics(result):
        if row.field == field:
            return row
    raise AssertionError(f"No diagnostic row for {field}")
