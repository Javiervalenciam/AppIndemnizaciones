from __future__ import annotations

from decimal import Decimal

from app_indemnizaciones.services.cetil_extractor import CetilExtractor, PdfReadResult
from app_indemnizaciones.services.cetil_models import ExtractionIssueCode, IssueSeverity
from app_indemnizaciones.services.cetil_ocr import OCR_NO_TEXT, OCR_UNAVAILABLE, OcrAttempt

_OCR_TEXT = """
CERTIFICACIÓN ELECTRÓNICA DE TIEMPOS LABORADOS
PERIODOS CERTIFICADOS
01-01-1980 31-12-1980 LABORAL PÚBLICO AUXILIAR
ENTIDAD RESPONSABLE: MUNICIPIO DE PRUEBA 0
FACTORES SALARIALES 1980
ASIGNACIÓN BÁSICA MENSUAL 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00
Total Devengado 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00 1,000.00
"""


def test_ocr_aplicado_exige_revision_manual():
    result = CetilExtractor().extract_from_pages({1: _OCR_TEXT}, ocr_applied=True)

    issue = next(
        issue
        for issue in result.issues
        if issue.code is ExtractionIssueCode.OCR_APPLIED_REVIEW_REQUIRED
    )
    assert issue.severity is IssueSeverity.REVIEW_REQUIRED
    assert "OCR" in issue.message
    assert issue.action
    assert result.periodos_certificados
    assert result.confidence_score < 1.0


def test_sin_texto_y_ocr_no_disponible_bloquea_con_accion():
    result = CetilExtractor().extract_from_pages(
        {1: ""},
        ocr_error_code=OCR_UNAVAILABLE,
        ocr_error_detail="El binario de Tesseract no está disponible.",
    )

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.code is ExtractionIssueCode.OCR_UNAVAILABLE
    assert issue.severity is IssueSeverity.BLOCK
    assert "pip install -e .[ocr]" in (issue.action or "")
    assert result.confidence_score == 0.0


def test_ocr_ejecutado_sin_texto_bloquea_con_codigo_propio():
    result = CetilExtractor().extract_from_pages(
        {1: ""},
        ocr_error_code=OCR_NO_TEXT,
    )

    assert result.issues[0].code is ExtractionIssueCode.OCR_NO_TEXT
    assert result.issues[0].severity is IssueSeverity.BLOCK


def test_extract_from_bytes_intenta_ocr_si_no_hay_capa_de_texto(monkeypatch):
    empty_read = PdfReadResult(pages={1: ""}, tables_by_page={}, reader="pymupdf")
    monkeypatch.setattr(CetilExtractor, "_read_pdf", staticmethod(lambda content: empty_read))
    monkeypatch.setattr(
        "app_indemnizaciones.services.cetil_extractor.ocr_pdf_pages",
        lambda content: OcrAttempt(pages={1: _OCR_TEXT}, engine_available=True),
    )

    result = CetilExtractor().extract_from_bytes(b"%PDF-1.4")

    assert any(
        issue.code is ExtractionIssueCode.OCR_APPLIED_REVIEW_REQUIRED
        for issue in result.issues
    )
    assert result.filas_liquidables_anuales
    assert result.filas_liquidables_anuales[0].ibl_reportado == Decimal("1000.00")
