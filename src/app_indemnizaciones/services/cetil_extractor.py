from __future__ import annotations

import re
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF

from app_indemnizaciones.domain.exceptions import CetilExtractionError, InvalidCetilFileError
from app_indemnizaciones.services.cetil_models import (
    MESES,
    CetilExtractionResult,
    CetilFactorSalarial,
    CetilPeriodoCertificado,
    CetilTrabajador,
)
from app_indemnizaciones.utils.dates import parse_date
from app_indemnizaciones.utils.money import parse_money

try:  # pdfplumber preserves table text better for many CETIL PDFs.
    import pdfplumber
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent.
    pdfplumber = None

_DATE_RE = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b")
_MONEY_RE = re.compile(r"(?<![\w-])(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{2})(?![\w-])")
_FACTOR_HEADER_RE = re.compile(r"FACTORES\s+SALARIALES\s+(?P<anio>\d{4})", re.IGNORECASE)
_PERIODO_LINE_RE = re.compile(
    r"(?P<desde>\d{2}[-/]\d{2}[-/]\d{4})\s+"
    r"(?P<hasta>\d{2}[-/]\d{2}[-/]\d{4})\s+"
    r"(?P<resto>.+)$",
    re.IGNORECASE,
)
_TIPO_EMPLEADO_RE = re.compile(r"\b(P[ÚU]BLICO|PRIVADO)\b", re.IGNORECASE)


class CetilExtractor:
    """Extractor CETIL tolerante: estructura datos para revisión, no calcula."""

    def extract(self, pdf_path: str | Path) -> CetilExtractionResult:
        path = Path(pdf_path)
        if not path.exists():
            raise InvalidCetilFileError(f"No existe el archivo CETIL: {path}")
        if path.suffix.lower() != ".pdf":
            raise InvalidCetilFileError("El archivo CETIL debe ser un PDF.")
        return self.extract_from_bytes(path.read_bytes())

    def extract_from_bytes(self, content: bytes) -> CetilExtractionResult:
        if not content:
            raise InvalidCetilFileError("El PDF CETIL está vacío.")
        try:
            pages = self._extract_text_pages(content)
        except Exception as exc:
            raise CetilExtractionError("No se pudo leer el PDF CETIL.") from exc
        return self.extract_from_pages(pages)

    def extract_from_pages(self, pages: dict[int, str]) -> CetilExtractionResult:
        text_pages = {page: text or "" for page, text in pages.items()}
        full_text = "\n".join(text_pages.values())
        advertencias: list[str] = []

        trabajador = self._extract_trabajador(full_text, advertencias)
        entidad_certificadora = self._extract_section_value(full_text, "DATOS DE LA ENTIDAD CERTIFICADORA")
        entidad_empleadora = self._extract_section_value(full_text, "DATOS DE LA ENTIDAD EMPLEADORA")
        periodos = self._extract_periodos(text_pages, advertencias)
        factores = self._extract_factores(text_pages, advertencias)

        if not periodos:
            advertencias.append("No se detectaron periodos certificados.")
        if not factores:
            advertencias.append("No se detectaron bloques de factores salariales.")
        if periodos:
            advertencias.append(
                "Se detectaron periodos, pero faltan salarios/IBL. Revise manualmente la tabla antes de calcular."
            )
        if factores:
            advertencias.append(
                "La asociación de factores salariales al IBL queda pendiente de confirmación funcional."
            )

        return CetilExtractionResult(
            trabajador=trabajador,
            entidad_empleadora=entidad_empleadora,
            entidad_certificadora=entidad_certificadora,
            periodos_certificados=periodos,
            factores_salariales=factores,
            advertencias=_dedupe(advertencias),
            texto_paginas=text_pages,
            confidence_score=self._confidence_score(periodos, factores),
        )

    @staticmethod
    def _extract_text_pages(content: bytes) -> dict[int, str]:
        if pdfplumber is not None:
            with pdfplumber.open(BytesIO(content)) as pdf:
                return {
                    page_number: page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    for page_number, page in enumerate(pdf.pages, start=1)
                }

        pages: dict[int, str] = {}
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page_number, page in enumerate(doc, start=1):
                pages[page_number] = page.get_text("text")
        return pages

    @staticmethod
    def _extract_section_value(text: str, heading: str) -> str | None:
        pattern = re.compile(rf"{re.escape(heading)}\s*\n(?P<value>.+)", re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return None
        value = match.group("value").strip()
        return value[:180] or None

    def _extract_trabajador(self, text: str, advertencias: list[str]) -> CetilTrabajador | None:
        documento_match = re.search(
            r"(?:TIPO\s+DOCUMENTO|TIPO\s+DE\s+DOCUMENTO|DOCUMENTO)\s*:?\s*"
            r"(?P<tipo>C\.?C\.?|CC|CE|TI|PA|C[EÉ]DULA)?\s*"
            r"(?:N[Oº°.]?|N[ÚU]MERO)?\s*:?\s*(?P<documento>\d[\d. -]{3,})",
            text,
            re.IGNORECASE,
        )
        fecha_match = re.search(
            r"FECHA\s+(?:DE\s+)?NACIMIENTO\s*:?\s*(?P<fecha>\d{2}[-/]\d{2}[-/]\d{4})",
            text,
            re.IGNORECASE,
        )

        primer_apellido = _field_value(text, "PRIMER APELLIDO")
        segundo_apellido = _field_value(text, "SEGUNDO APELLIDO")
        primer_nombre = _field_value(text, "PRIMER NOMBRE")
        segundo_nombre = _field_value(text, "SEGUNDO NOMBRE")
        nombre_completo = _build_nombre_completo(
            primer_nombre,
            segundo_nombre,
            primer_apellido,
            segundo_apellido,
        ) or _field_value(text, "NOMBRE COMPLETO")

        fecha_nacimiento = None
        if fecha_match:
            try:
                fecha_nacimiento = parse_date(fecha_match.group("fecha"))
            except ValueError:
                advertencias.append("No fue posible normalizar la fecha de nacimiento detectada.")

        if not any([documento_match, nombre_completo, fecha_nacimiento]):
            advertencias.append("No se detectaron datos básicos del trabajador con alta confianza.")
            return None

        return CetilTrabajador(
            tipo_documento=_normalize_doc_type(documento_match.group("tipo")) if documento_match else None,
            documento=_clean_document(documento_match.group("documento")) if documento_match else None,
            primer_apellido=primer_apellido,
            segundo_apellido=segundo_apellido,
            primer_nombre=primer_nombre,
            segundo_nombre=segundo_nombre,
            nombre_completo=nombre_completo,
            fecha_nacimiento=fecha_nacimiento,
        )

    def _extract_periodos(
        self,
        pages: dict[int, str],
        advertencias: list[str],
    ) -> list[CetilPeriodoCertificado]:
        periodos: list[CetilPeriodoCertificado] = []
        for page_number, text in pages.items():
            for line in _candidate_period_lines(text.splitlines()):
                match = _PERIODO_LINE_RE.search(line)
                if not match:
                    continue
                try:
                    fecha_desde = parse_date(match.group("desde"))
                    fecha_hasta = parse_date(match.group("hasta"))
                except ValueError:
                    advertencias.append(f"No fue posible normalizar un periodo en página {page_number}.")
                    continue

                parsed_remainder = _parse_period_remainder(match.group("resto"))
                periodos.append(
                    CetilPeriodoCertificado(
                        fecha_desde=fecha_desde,
                        fecha_hasta=fecha_hasta,
                        tipo_vinculacion=parsed_remainder["tipo_vinculacion"],
                        tipo_empleado=parsed_remainder["tipo_empleado"],
                        cargo=parsed_remainder["cargo"],
                        entidad_responsable=parsed_remainder["entidad_responsable"],
                        total_no_dias=parsed_remainder["total_no_dias"],
                        fuente_pagina=page_number,
                        raw_text=line,
                    )
                )
        return periodos

    def _extract_factores(
        self,
        pages: dict[int, str],
        advertencias: list[str],
    ) -> list[CetilFactorSalarial]:
        factores: list[CetilFactorSalarial] = []
        for page_number, text in pages.items():
            blocks = _factor_blocks(text)
            for anio, block in blocks:
                for concepto in ("ASIGNACIÓN BÁSICA MENSUAL", "Total Devengado"):
                    raw_line = _concept_context(block, concepto)
                    if not raw_line:
                        continue
                    monthly_values = _monthly_values(raw_line, advertencias, anio, concepto)
                    factores.append(
                        CetilFactorSalarial(
                            anio=anio,
                            concepto=concepto,
                            valores_mensuales=monthly_values,
                            total_devengado_mensual=monthly_values
                            if concepto.lower() == "total devengado"
                            else {},
                            fuente_pagina=page_number,
                            raw_text=raw_line,
                        )
                    )
        return factores

    @staticmethod
    def _confidence_score(
        periodos: list[CetilPeriodoCertificado],
        factores: list[CetilFactorSalarial],
    ) -> float:
        score = 0.0
        if periodos:
            score += 0.55
        if factores:
            score += 0.30
        if any(periodo.cargo for periodo in periodos):
            score += 0.10
        if any(periodo.entidad_responsable for periodo in periodos):
            score += 0.05
        return min(score, 1.0)


def _candidate_period_lines(lines: Iterable[str]) -> Iterable[str]:
    for line in lines:
        normalized = " ".join(line.strip().split())
        if len(_DATE_RE.findall(normalized)) >= 2:
            yield normalized


def _parse_period_remainder(resto: str) -> dict[str, str | int | None]:
    normalized = " ".join(resto.split())
    tipo_empleado_match = _TIPO_EMPLEADO_RE.search(normalized)
    tipo_vinculacion = None
    tipo_empleado = None
    after_tipo = normalized

    if tipo_empleado_match:
        tipo_empleado = tipo_empleado_match.group(1).upper().replace("PUBLICO", "PÚBLICO")
        tipo_vinculacion = normalized[: tipo_empleado_match.start()].strip() or None
        after_tipo = normalized[tipo_empleado_match.end() :].strip()

    total_no_dias = _last_int(after_tipo)
    text_without_tail_numbers = re.sub(r"\b\d+\b(?:\s+\w+){0,3}$", "", after_tipo).strip()
    entidad = _extract_labeled_value(text_without_tail_numbers, "ENTIDAD RESPONSABLE")
    cargo = _extract_labeled_value(text_without_tail_numbers, "CARGO")

    if not cargo and text_without_tail_numbers:
        cargo = text_without_tail_numbers
    if entidad and cargo:
        cargo = cargo.replace(entidad, "").strip() or cargo

    return {
        "tipo_vinculacion": tipo_vinculacion,
        "tipo_empleado": tipo_empleado,
        "cargo": cargo or None,
        "entidad_responsable": entidad,
        "total_no_dias": total_no_dias,
    }


def _factor_blocks(text: str) -> list[tuple[int, str]]:
    matches = list(_FACTOR_HEADER_RE.finditer(text))
    blocks: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((int(match.group("anio")), text[start:end]))
    return blocks


def _concept_context(block: str, concept: str) -> str | None:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if concept.lower() not in line.lower():
            continue
        context = [line.strip()]
        for following in lines[index + 1 : index + 4]:
            if _FACTOR_HEADER_RE.search(following):
                break
            if any(marker.lower() in following.lower() for marker in ("ASIGNACIÓN", "Total Devengado")):
                break
            context.append(following.strip())
            if len(_MONEY_RE.findall(" ".join(context))) >= 12:
                break
        return " ".join(part for part in context if part)
    return None


def _monthly_values(
    text: str,
    advertencias: list[str],
    anio: int,
    concepto: str,
) -> dict[str, object]:
    values = [parse_money(value) for value in _MONEY_RE.findall(text)]
    if len(values) != 12:
        advertencias.append(
            "No fue posible asociar todos los valores salariales a meses con alta confianza "
            f"para {concepto} {anio}."
        )
    return {month: values[index] if index < len(values) else None for index, month in enumerate(MESES)}


def _field_value(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*:?\s*(?P<value>[A-ZÁÉÍÓÚÑ ]+)", text, re.IGNORECASE)
    if not match:
        return None
    value = " ".join(match.group("value").split())
    return value.title() if value else None


def _build_nombre_completo(*parts: str | None) -> str | None:
    values = [part for part in parts if part]
    return " ".join(values) if values else None


def _normalize_doc_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.upper().replace(".", "")
    return "CC" if normalized in {"CÉDULA", "CEDULA"} else normalized


def _clean_document(value: str) -> str:
    return re.sub(r"\D", "", value)


def _extract_labeled_value(text: str, label: str) -> str | None:
    match = re.search(rf"{label}\s*:?\s*(?P<value>[A-ZÁÉÍÓÚÑ0-9 .-]+)", text, re.IGNORECASE)
    if not match:
        return None
    value = " ".join(match.group("value").split())
    return value.title() if value else None


def _last_int(text: str) -> int | None:
    matches = re.findall(r"\b\d+\b", text)
    return int(matches[-1]) if matches else None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
