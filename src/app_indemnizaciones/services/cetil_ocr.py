"""OCR opcional para CETIL escaneados sin capa de texto.

El OCR nunca reemplaza la revisión humana: si se aplica, el extractor marca
la extracción con ``CETIL_OCR_APPLIED_REVIEW_REQUIRED`` y el usuario debe
comparar cada campo contra el PDF original.

Las dependencias son opcionales (``pip install -e .[ocr]``) y también se
requiere el binario de Tesseract disponible en ``PATH``. Si faltan, se
devuelve un error tipificado para que el extractor bloquee con una acción
clara en lugar de inventar datos.
"""

from __future__ import annotations

from dataclasses import dataclass

OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
OCR_FAILED = "OCR_FAILED"
OCR_NO_TEXT = "OCR_NO_TEXT"


@dataclass(frozen=True)
class OcrAttempt:
    """Resultado de intentar OCR sobre un PDF."""

    pages: dict[int, str]
    engine_available: bool
    error_code: str | None = None
    detail: str | None = None


def ocr_pdf_pages(
    content: bytes,
    *,
    language: str = "spa",
    dpi: int = 300,
    max_pages: int = 60,
) -> OcrAttempt:
    """Convierte cada página del PDF a imagen y extrae texto con Tesseract."""
    if not content:
        return OcrAttempt({}, engine_available=False, error_code=OCR_NO_TEXT, detail="PDF vacío.")

    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        return OcrAttempt(
            {},
            engine_available=False,
            error_code=OCR_UNAVAILABLE,
            detail=f"Falta una dependencia del extra OCR: {exc.name}.",
        )

    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001 - Tesseract no está instalado o no está en PATH
        return OcrAttempt(
            {},
            engine_available=False,
            error_code=OCR_UNAVAILABLE,
            detail=f"El binario de Tesseract no está disponible: {exc}.",
        )

    pages: dict[int, str] = {}
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            for number, page in enumerate(doc, start=1):
                if number > max_pages:
                    break
                pixmap = page.get_pixmap(dpi=dpi)
                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )
                pages[number] = pytesseract.image_to_string(image, lang=language) or ""
    except Exception as exc:  # noqa: BLE001 - se reporta como fallo de OCR
        return OcrAttempt(
            pages,
            engine_available=True,
            error_code=OCR_FAILED,
            detail=f"El OCR falló al procesar el PDF: {exc}.",
        )

    if not any(text.strip() for text in pages.values()):
        return OcrAttempt(
            pages,
            engine_available=True,
            error_code=OCR_NO_TEXT,
            detail="El OCR no reconoció texto legible en ninguna página.",
        )
    return OcrAttempt(pages, engine_available=True)
