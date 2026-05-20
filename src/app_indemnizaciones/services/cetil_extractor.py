from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass(frozen=True)
class CetilExtractionResult:
    text: str
    periodos_raw: list[dict[str, str]]
    factores_salariales_raw: dict[int, str]
    warnings: list[str]


class CetilExtractor:
    """
    First-pass CETIL extractor.

    This module intentionally returns raw extraction blocks for manual review.
    The next step is to replace/extend regex extraction with table-aware extraction
    for PDFs with complex layout.
    """

    PERIODO_RE = re.compile(
        r"(?P<desde>\d{2}-\d{2}-\d{4})\s+"
        r"(?P<hasta>\d{2}-\d{2}-\d{4})\s+"
        r"(?P<tipo_vinculacion>[A-ZÁÉÍÓÚÑ ]+)\s+"
        r"(?P<tipo_empleado>PÚBLICO|PUBLICO|PRIVADO)?\s*"
        r"(?P<resto>.+?)(?=\n|$)",
        re.MULTILINE,
    )
    FACTORES_RE = re.compile(
        r"FACTORES SALARIALES\s+(?P<year>\d{4}).*?(?=FACTORES SALARIALES\s+\d{4}|INFORMACIÓN VÁLIDA|FUNCIONARIO COMPETENTE|$)",
        re.DOTALL | re.IGNORECASE,
    )

    def extract(self, pdf_path: str | Path) -> CetilExtractionResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"No existe el archivo CETIL: {path}")

        text = self._extract_text(path)
        periodos = [match.groupdict() for match in self.PERIODO_RE.finditer(text)]
        factores = {
            int(match.group("year")): match.group(0).strip()
            for match in self.FACTORES_RE.finditer(text)
        }

        warnings: list[str] = []
        if not periodos:
            warnings.append("No se detectaron periodos certificados de forma automática.")
        if not factores:
            warnings.append("No se detectaron bloques de factores salariales.")

        return CetilExtractionResult(
            text=text,
            periodos_raw=periodos,
            factores_salariales_raw=factores,
            warnings=warnings,
        )

    @staticmethod
    def _extract_text(path: Path) -> str:
        chunks: list[str] = []
        with fitz.open(path) as doc:
            for page in doc:
                chunks.append(page.get_text("text"))
        return "\n".join(chunks)
