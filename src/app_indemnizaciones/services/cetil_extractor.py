from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF

from app_indemnizaciones.domain.exceptions import CetilExtractionError, InvalidCetilFileError
from app_indemnizaciones.services.cetil_models import (
    MESES,
    CetilEntidadEmpleadora,
    CetilExtractionResult,
    CetilFactorSalarial,
    CetilMetadata,
    CetilPeriodoCertificado,
    CetilTrabajador,
)
from app_indemnizaciones.services.period_normalizer import normalize_cetil_to_annual_periods
from app_indemnizaciones.utils.dates import parse_date
from app_indemnizaciones.utils.money import parse_money

try:  # pdfplumber preserves table text better for many CETIL PDFs.
    import pdfplumber
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent.
    pdfplumber = None

_DATE_RE = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b")
_MONEY_RE = re.compile(
    r"(?<![\w-])\$?\s*(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{2})?(?![\w-])"
)
_FACTOR_HEADER_RE = re.compile(r"FACTORES\s+SALARIALES\s+(?P<anio>\d{4})", re.IGNORECASE)
_SALARY_BLOCK_END_RE = re.compile(
    r"INFORMACI[ÓO]N\s+V[ÁA]LIDA\s+[ÚU]NICAMENTE|"
    r"POSIBLE\s+FECHA\s+BASE|"
    r"POSIBLE\s+SALARIO\s+BASE|"
    r"FUNCIONARIO\s+COMPETENTE\s+PARA\s+CERTIFICAR|"
    r"^\s*CERTIFICACION\s*$|"
    r"NOTAS\s+ADICIONALES",
    re.IGNORECASE | re.MULTILINE,
)
_REPEATED_CETIL_HEADER_RE = re.compile(
    r"^\s*(?:"
    r"CERTIFICACI[ÓO]N\s+ELECTR[ÓO]NICA\s+DE\s+TIEMPOS\s+LABORADOS|"
    r"CETIL|"
    r"Oficina\s+de\s+Bonos\s+Pensionales.*|"
    r"Ciudad\s+y\s+fecha\s+de\s+expedici[óo]n.*|"
    r"No\.\s*\d+|"
    r"Pag\.\s*\d+"
    r")\s*$",
    re.IGNORECASE,
)
_PERIODO_LINE_RE = re.compile(
    r"(?P<desde>\d{2}[-/]\d{2}[-/]\d{4})\s+"
    r"(?P<hasta>\d{2}[-/]\d{2}[-/]\d{4})\s+"
    r"(?P<resto>.+)$",
    re.IGNORECASE,
)
_TIPO_EMPLEADO_RE = re.compile(r"\b(P[ÚU]BLICO|PRIVADO)\b", re.IGNORECASE)
_ENTITY_RE = re.compile(
    r"\b(?P<entity>(?:MUNICIPIO|ALCALD[IÍ]A|GOBERNACI[ÓO]N|DEPARTAMENTO)\s+DE\s+"
    r"[A-ZÁÉÍÓÚÑ ]+?)(?=\s+\d+\b|\s+\b(?:NO|SI|S[IÍ]|NINGUNO)\b|$)",
    re.IGNORECASE,
)
_PERSON_LABELS = (
    "DATOS DEL EMPLEADO",
    "PERIODOS CERTIFICADOS",
    "Tipo de Documento",
    "Documento",
    "Fecha de Nacimiento",
    "Primer Apellido",
    "Segundo Apellido",
    "Primer Nombre",
    "Segundo Nombre",
    "Nombre",
    "Nit",
    "Desde",
    "Hasta",
    "Cargo",
    "Aportes",
    "Fondo",
    "Entidad Responsable",
)
_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


@dataclass(frozen=True)
class SalaryBlockRaw:
    anio: int
    start_page: int
    end_page: int
    raw_text: str
    warnings: tuple[str, ...] = ()


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
            pages, tables_by_page = self._extract_pdf_content(content)
        except Exception as exc:
            raise CetilExtractionError("No se pudo leer el PDF CETIL.") from exc
        return self.extract_from_pages(pages, tables_by_page=tables_by_page)

    def extract_from_pages(
        self,
        pages: dict[int, str],
        tables_by_page: dict[int, list[list[list[str | None]]]] | None = None,
    ) -> CetilExtractionResult:
        text_pages = {page: text or "" for page, text in pages.items()}
        full_text = "\n".join(text_pages.values())
        advertencias: list[str] = []

        metadata = self._extract_metadata(full_text, advertencias)
        trabajador = self._extract_trabajador(full_text, advertencias)
        entidad_certificadora = self._extract_section_value(full_text, "DATOS DE LA ENTIDAD CERTIFICADORA")
        entidad_empleadora = self._extract_entidad_empleadora(full_text, advertencias)
        periodos = self._extract_periodos(text_pages, advertencias, tables_by_page=tables_by_page)
        factores = self._extract_factores(text_pages, advertencias)
        factores = _apply_ibl_sugerido(factores, advertencias)

        if not periodos:
            advertencias.append("No se detectaron periodos certificados.")
        if not factores:
            advertencias.append("No se detectaron bloques de factores salariales.")
        if periodos and not factores:
            advertencias.append(
                "Se detectaron periodos, pero no se detectaron factores salariales. "
                "Revise manualmente la tabla antes de calcular."
            )

        result = CetilExtractionResult(
            metadata=metadata,
            trabajador=trabajador,
            entidad_empleadora=entidad_empleadora,
            entidad_certificadora=entidad_certificadora,
            periodos_certificados=periodos,
            factores_salariales=factores,
            advertencias=_dedupe(advertencias),
            texto_paginas=text_pages,
            confidence_score=self._confidence_score(periodos, factores),
        )
        filas, annual_warnings = normalize_cetil_to_annual_periods(result)
        return replace(
            result,
            filas_liquidables_anuales=filas,
            advertencias=_dedupe([*result.advertencias, *annual_warnings]),
        )

    @staticmethod
    def _extract_pdf_content(
        content: bytes,
    ) -> tuple[dict[int, str], dict[int, list[list[list[str | None]]]]]:
        if pdfplumber is not None:
            with pdfplumber.open(BytesIO(content)) as pdf:
                text_pages: dict[int, str] = {}
                tables_by_page: dict[int, list[list[list[str | None]]]] = {}
                for page_number, page in enumerate(pdf.pages, start=1):
                    text_pages[page_number] = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    tables_by_page[page_number] = page.extract_tables() or []
                return text_pages, tables_by_page

        pages: dict[int, str] = {}
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page_number, page in enumerate(doc, start=1):
                pages[page_number] = page.get_text("text")
        return pages, {}

    @staticmethod
    def _extract_text_pages(content: bytes) -> dict[int, str]:
        pages, _tables = CetilExtractor._extract_pdf_content(content)
        return pages

    @staticmethod
    def _extract_section_value(text: str, heading: str) -> str | None:
        pattern = re.compile(rf"{re.escape(heading)}\s*\n(?P<value>.+)", re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return None
        value = match.group("value").strip()
        return value[:180] or None

    def _extract_metadata(self, text: str, advertencias: list[str]) -> CetilMetadata:
        numero_match = re.search(
            r"(?:CETIL\s*)?N[Oº°]?\.?\s*:?\s*(?P<numero>\d{8,})",
            text,
            re.IGNORECASE,
        )
        expedition_match = re.search(
            r"Ciudad\s+y\s+fecha\s+de\s+expedici[oó]n\s*:?\s*"
            r"(?P<ciudad>[A-ZÁÉÍÓÚÑ .-]+?)\s*,\s*"
            r"(?P<fecha>[A-Za-zÁÉÍÓÚÑáéíóúñ]+\s+\d{1,2}\s+de\s+\d{4})",
            text,
            re.IGNORECASE,
        )

        fecha_expedicion = None
        if expedition_match:
            fecha_expedicion = _parse_spanish_text_date(expedition_match.group("fecha"), advertencias)

        return CetilMetadata(
            numero_cetil=numero_match.group("numero") if numero_match else None,
            ciudad_expedicion=expedition_match.group("ciudad").strip().upper()
            if expedition_match
            else None,
            fecha_expedicion_cetil=fecha_expedicion,
        )

    def _extract_trabajador(self, text: str, advertencias: list[str]) -> CetilTrabajador | None:
        employee_block = _block_between(text, "DATOS DEL EMPLEADO", ("PERIODOS CERTIFICADOS",))
        search_text = employee_block or text

        documento = _extract_document_number(search_text)
        tipo_documento = _extract_tipo_documento(search_text)
        fecha_nacimiento = _extract_labeled_date(
            search_text,
            "Fecha de Nacimiento",
            advertencias,
            error_message="No fue posible normalizar la fecha de nacimiento detectada.",
        )
        genero = (
            _extract_labeled_text(search_text, "GÉNERO", _PERSON_LABELS)
            or _extract_labeled_text(search_text, "GENERO", _PERSON_LABELS)
            or _extract_labeled_text(search_text, "SEXO", _PERSON_LABELS)
        )
        if not genero:
            advertencias.append("No se detectó campo explícito de género en el CETIL.")

        primer_apellido = clean_person_name_part(
            _extract_labeled_text(search_text, "Primer Apellido", _PERSON_LABELS)
        )
        segundo_apellido = clean_person_name_part(
            _extract_labeled_text(search_text, "Segundo Apellido", _PERSON_LABELS)
        )
        primer_nombre = clean_person_name_part(
            _extract_labeled_text(search_text, "Primer Nombre", _PERSON_LABELS)
        )
        segundo_nombre = clean_person_name_part(
            _extract_labeled_text(search_text, "Segundo Nombre", _PERSON_LABELS)
        )
        nombre_completo = _build_nombre_completo(
            primer_nombre,
            segundo_nombre,
            primer_apellido,
            segundo_apellido,
        ) or clean_cetil_value(_extract_labeled_text(search_text, "Nombre Completo", _PERSON_LABELS))

        if not any([documento, nombre_completo, fecha_nacimiento]):
            advertencias.append("No se detectaron datos básicos del trabajador con alta confianza.")
            return None

        return CetilTrabajador(
            tipo_documento=_normalize_doc_type(tipo_documento),
            documento=documento,
            primer_apellido=primer_apellido,
            segundo_apellido=segundo_apellido,
            primer_nombre=primer_nombre,
            segundo_nombre=segundo_nombre,
            nombre_completo=nombre_completo,
            fecha_nacimiento=fecha_nacimiento,
            genero=genero,
        )

    def _extract_entidad_empleadora(
        self,
        text: str,
        advertencias: list[str],
    ) -> CetilEntidadEmpleadora | None:
        section = _block_between(
            text,
            "DATOS DE LA ENTIDAD EMPLEADORA",
            ("DATOS DEL EMPLEADO", "PERIODOS CERTIFICADOS"),
        )
        if not section:
            advertencias.append("No se detectó sección de entidad empleadora en el CETIL.")
            return None

        nombre = (
            _extract_labeled_text(section, "Nombre Entidad Empleadora", ("Nit",))
            or _extract_labeled_text(section, "Nombre de la Entidad Empleadora", ("Nit",))
            or _extract_labeled_text(
                section,
                "Nombre",
                ("Nit", "Fecha en que entró en vigencia", "el Sistema General de Pensiones"),
            )
            or _extract_labeled_text(section, "Razón Social", ("Nit",))
            or _extract_labeled_text(section, "Razon Social", ("Nit",))
            or _extract_public_entity(section)
        )
        nombre = _clean_public_entity_name(nombre)
        nit = _extract_nit(section)
        fecha_vigencia = _extract_vigencia_pensional(section, advertencias)

        if not nombre:
            advertencias.append("No se detectó nombre de entidad empleadora.")
        if not nit:
            advertencias.append("No se detectó NIT de entidad empleadora.")

        return CetilEntidadEmpleadora(
            nombre_entidad_empleadora=nombre,
            nit_entidad_empleadora=nit,
            fecha_vigencia_sistema_general_pensiones=fecha_vigencia,
        )

    def _extract_periodos(
        self,
        pages: dict[int, str],
        advertencias: list[str],
        tables_by_page: dict[int, list[list[list[str | None]]]] | None = None,
    ) -> list[CetilPeriodoCertificado]:
        periodos_from_tables = _extract_periodos_from_tables(tables_by_page or {}, advertencias)
        if periodos_from_tables:
            return periodos_from_tables

        periodos: list[CetilPeriodoCertificado] = []
        for page_number, text in pages.items():
            period_block = _block_between(text, "PERIODOS CERTIFICADOS", ("FACTORES SALARIALES",))
            lines = period_block.splitlines() if period_block else text.splitlines()
            for line in _candidate_period_lines(lines):
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
        salary_blocks = extract_salary_blocks_across_pages(pages)
        for salary_block in salary_blocks:
            advertencias.extend(salary_block.warnings)
            block_has_values = False
            for concepto in ("ASIGNACIÓN BÁSICA MENSUAL", "Total Devengado"):
                raw_line = _concept_context(salary_block.raw_text, concepto)
                if not raw_line:
                    continue
                values = _money_values(raw_line)
                monthly_values = _monthly_values(values, advertencias, salary_block.anio, concepto)
                selected_value = _select_suggested_value(values)
                is_total_devengado = concepto.lower() == "total devengado"
                factores.append(
                    CetilFactorSalarial(
                        anio=salary_block.anio,
                        concepto=concepto,
                        valores_mensuales=monthly_values,
                        valores_encontrados=values,
                        asignacion_basica_mensual=None
                        if is_total_devengado
                        else selected_value,
                        total_devengado=selected_value if is_total_devengado else None,
                        total_devengado_mensual=monthly_values if is_total_devengado else {},
                        fuente_pagina=salary_block.start_page,
                        raw_text=raw_line,
                    )
                )
                if any(value > 0 for value in values):
                    block_has_values = True
            if not block_has_values:
                advertencias.append(
                    f"No se detectaron valores salariales positivos para el año {salary_block.anio}."
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
    entity_match = _ENTITY_RE.search(text_without_tail_numbers)
    if not entidad and entity_match:
        entidad = _clean_public_entity_name(entity_match.group("entity"))

    cargo = _extract_labeled_value(text_without_tail_numbers, "CARGO")

    if not cargo and text_without_tail_numbers:
        if entity_match:
            cargo_source = text_without_tail_numbers[: entity_match.start()]
        else:
            cargo_source = re.split(
                r"\bENTIDAD\s+RESPONSABLE\b\s*:?",
                text_without_tail_numbers,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
        cargo = _clean_period_cargo(cargo_source)

    return {
        "tipo_vinculacion": tipo_vinculacion,
        "tipo_empleado": tipo_empleado,
        "cargo": _clean_period_cargo(cargo) if cargo else None,
        "entidad_responsable": entidad,
        "total_no_dias": total_no_dias,
    }


def _extract_periodos_from_tables(
    tables_by_page: dict[int, list[list[list[str | None]]]],
    advertencias: list[str],
) -> list[CetilPeriodoCertificado]:
    periodos: list[CetilPeriodoCertificado] = []
    for page_number, tables in tables_by_page.items():
        for table in tables:
            if not _looks_like_period_table(table):
                continue
            for row in table[2:]:
                if not row or len(row) < 10 or not row[0] or not row[1]:
                    continue
                try:
                    fecha_desde = parse_date(row[0])
                    fecha_hasta = parse_date(row[1])
                except ValueError:
                    advertencias.append(f"No fue posible normalizar un periodo en página {page_number}.")
                    continue

                periodos.append(
                    CetilPeriodoCertificado(
                        fecha_desde=fecha_desde,
                        fecha_hasta=fecha_hasta,
                        tipo_vinculacion=clean_cetil_value(row[2]),
                        tipo_empleado=clean_cetil_value(row[3]),
                        cargo=_clean_period_cargo(row[4]),
                        aportes_pension=clean_cetil_value(row[5]),
                        aportes_salud=clean_cetil_value(row[6]),
                        aportes_riesgos=clean_cetil_value(row[7]),
                        fondo_aporte=clean_cetil_value(row[8]),
                        entidad_responsable=_clean_public_entity_name(row[9]),
                        total_no_dias=int(row[10]) if len(row) > 10 and str(row[10]).isdigit() else None,
                        cargo_alto_riesgo=clean_cetil_value(row[11]) if len(row) > 11 else None,
                        tiempo_completo=clean_cetil_value(row[12]) if len(row) > 12 else None,
                        horas_semanales_laboradas=clean_cetil_value(row[13]) if len(row) > 13 else None,
                        fuente_pagina=page_number,
                        raw_text=" | ".join(clean_cetil_value(value) or "" for value in row),
                    )
                )
    return periodos


def _looks_like_period_table(table: list[list[str | None]]) -> bool:
    if len(table) < 3:
        return False
    first_row = " ".join(clean_cetil_value(value) or "" for value in table[0])
    header = " ".join(clean_cetil_value(value) or "" for value in table[1])
    return "PERIODOS CERTIFICADOS" in first_row.upper() or (
        "DESDE" in header.upper()
        and "HASTA" in header.upper()
        and "ENTIDAD RESPONSABLE" in header.upper()
    )


def extract_salary_blocks_across_pages(pages_text: dict[int, str]) -> list[SalaryBlockRaw]:
    blocks: list[SalaryBlockRaw] = []
    active_year: int | None = None
    active_start_page: int | None = None
    active_end_page: int | None = None
    active_parts: list[str] = []

    def close_active() -> None:
        nonlocal active_year, active_start_page, active_end_page, active_parts
        if active_year is None or active_start_page is None or active_end_page is None:
            return
        raw_text = "\n".join(part for part in active_parts if part.strip()).strip()
        if raw_text:
            warnings = ()
            if active_end_page > active_start_page:
                warnings = (
                    f"El bloque salarial {active_year} continúa entre páginas "
                    f"{active_start_page} y {active_end_page}.",
                )
            blocks.append(
                SalaryBlockRaw(
                    anio=active_year,
                    start_page=active_start_page,
                    end_page=active_end_page,
                    raw_text=raw_text,
                    warnings=warnings,
                )
            )
        active_year = None
        active_start_page = None
        active_end_page = None
        active_parts = []

    for page_number in sorted(pages_text):
        page_text = pages_text[page_number] or ""
        position = 0
        matches = list(_FACTOR_HEADER_RE.finditer(page_text))

        for match in matches:
            prefix = page_text[position : match.start()]
            if active_year is not None:
                append_text, should_close = _salary_text_until_cut(prefix, in_continuation=True)
                if append_text:
                    active_parts.append(append_text)
                    active_end_page = page_number
                close_active()
                if should_close:
                    position = match.end()
                    continue

            active_year = int(match.group("anio"))
            active_start_page = page_number
            active_end_page = page_number
            active_parts = []

            next_match_start = _next_match_start(matches, match)
            segment = page_text[match.start() : next_match_start if next_match_start is not None else len(page_text)]
            append_text, should_close = _salary_text_until_cut(segment, in_continuation=False)
            if append_text:
                active_parts.append(append_text)
            if should_close:
                close_active()
            position = next_match_start if next_match_start is not None else len(page_text)

        if active_year is not None and position < len(page_text):
            append_text, should_close = _salary_text_until_cut(
                page_text[position:],
                in_continuation=active_start_page != page_number,
            )
            if append_text:
                active_parts.append(append_text)
                active_end_page = page_number
            if should_close:
                close_active()

    close_active()
    return blocks


def _next_match_start(matches: list[re.Match[str]], current: re.Match[str]) -> int | None:
    for index, match in enumerate(matches):
        if match is current and index + 1 < len(matches):
            return matches[index + 1].start()
    return None


def _salary_text_until_cut(text: str, *, in_continuation: bool) -> tuple[str, bool]:
    cut_match = _SALARY_BLOCK_END_RE.search(text)
    selected = text[: cut_match.start()] if cut_match else text
    if in_continuation:
        selected = _strip_repeated_cetil_headers(selected)
    return selected.strip(), cut_match is not None


def _strip_repeated_cetil_headers(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if _REPEATED_CETIL_HEADER_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


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
    values: list[Decimal],
    advertencias: list[str],
    anio: int,
    concepto: str,
) -> dict[str, Decimal | None]:
    if len(values) != 12:
        advertencias.append(
            "No fue posible asociar todos los valores salariales a meses con alta confianza "
            f"para {concepto} {anio}."
        )
    return {month: values[index] if index < len(values) else None for index, month in enumerate(MESES)}


def _money_values(text: str) -> list[Decimal]:
    values: list[Decimal] = []
    for raw in _MONEY_RE.findall(text):
        value = parse_money(raw)
        if value is not None:
            values.append(value)
    return values


def _select_suggested_value(values: list[Decimal]) -> Decimal | None:
    positive_values = [value for value in values if value > 0]
    if not positive_values:
        return None

    counts = Counter(positive_values)
    most_common = counts.most_common()
    if not most_common:
        return None
    top_count = most_common[0][1]
    tied = [value for value, count in most_common if count == top_count]
    return tied[0] if len(tied) == 1 else None


def _apply_ibl_sugerido(
    factores: list[CetilFactorSalarial],
    advertencias: list[str],
) -> list[CetilFactorSalarial]:
    by_year: dict[int, list[CetilFactorSalarial]] = {}
    for factor in factores:
        by_year.setdefault(factor.anio, []).append(factor)

    selected_by_year: dict[int, Decimal | None] = {}
    for anio, year_factors in by_year.items():
        assignment = _find_factor(year_factors, "ASIGNACIÓN BÁSICA MENSUAL")
        total = _find_factor(year_factors, "Total Devengado")
        selected = _select_ibl_from_factor(assignment, anio, "ASIGNACIÓN BÁSICA MENSUAL", advertencias)
        if selected is None:
            selected = _select_ibl_from_factor(total, anio, "Total Devengado", advertencias)
        if selected is None:
            advertencias.append(f"No se detectó IBL para el año {anio}. Debe ingresarse manualmente.")
        selected_by_year[anio] = selected

    return [replace(factor, ibl_sugerido=selected_by_year.get(factor.anio)) for factor in factores]


def _select_ibl_from_factor(
    factor: CetilFactorSalarial | None,
    anio: int,
    label: str,
    advertencias: list[str],
) -> Decimal | None:
    if factor is None:
        return None

    positive_values = [value for value in factor.valores_encontrados if value > 0]
    if not positive_values:
        return None

    counts = Counter(positive_values)
    most_common = counts.most_common()
    top_count = most_common[0][1]
    tied = [value for value, count in most_common if count == top_count]
    if len(tied) > 1:
        advertencias.append(
            f"No se detectó IBL confiable para el año {anio}; empate entre valores de {label}."
        )
        return None
    if len(set(positive_values)) > 1:
        advertencias.append(
            f"IBL sugerido por valor positivo más frecuente en el año {anio}; "
            "se detectó posible valor atípico y debe revisarse manualmente."
        )
    return tied[0]


def _find_factor(
    factores: list[CetilFactorSalarial],
    concept: str,
) -> CetilFactorSalarial | None:
    for factor in factores:
        if factor.concepto.lower() == concept.lower():
            return factor
    return None


def _parse_spanish_text_date(text: str, advertencias: list[str]) -> date | None:
    match = re.search(
        r"(?P<month>[A-Za-zÁÉÍÓÚÑáéíóúñ]+)\s+(?P<day>\d{1,2})\s+de\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        advertencias.append(f"No fue posible normalizar fecha textual: {text}.")
        return None

    month = _SPANISH_MONTHS.get(match.group("month").lower())
    if month is None:
        advertencias.append(f"No fue posible reconocer el mes en fecha textual: {text}.")
        return None
    return date(int(match.group("year")), month, int(match.group("day")))


def clean_cetil_value(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\n", " ").split()).strip(" :")
    return text or None


def clean_person_name_part(value: object) -> str | None:
    text = clean_cetil_value(value)
    if not text:
        return None
    for label in _PERSON_LABELS:
        label_match = re.search(_label_pattern(label), text, re.IGNORECASE)
        if label_match:
            text = text[: label_match.start()].strip()
    text = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ ]+", " ", text)
    text = " ".join(text.split())
    return text.title() if text else None


def _block_between(text: str, start_heading: str, end_headings: tuple[str, ...]) -> str | None:
    start_match = re.search(_label_pattern(start_heading), text, re.IGNORECASE)
    if not start_match:
        return None
    start = start_match.end()
    end = len(text)
    for heading in end_headings:
        end_match = re.search(_label_pattern(heading), text[start:], re.IGNORECASE)
        if end_match:
            end = min(end, start + end_match.start())
    block = text[start:end].strip()
    return block or None


def _extract_labeled_text(text: str, label: str, stop_labels: tuple[str, ...]) -> str | None:
    stop_pattern = "|".join(_label_pattern(stop_label) for stop_label in stop_labels)
    pattern = re.compile(
        rf"{_label_pattern(label)}\s*:?\s*(?P<value>.*?)(?=(?:\s+(?:{stop_pattern})\s*:?)|\n|$)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    return clean_cetil_value(match.group("value"))


def _extract_labeled_date(
    text: str,
    label: str,
    advertencias: list[str],
    *,
    error_message: str,
) -> date | None:
    value = _extract_labeled_text(text, label, _PERSON_LABELS)
    if not value:
        return None
    date_match = re.search(
        r"\d{2}[-/]\d{2}[-/]\d{4}|[A-Za-zÁÉÍÓÚÑáéíóúñ]+\s+\d{1,2}\s+de\s+\d{4}",
        value,
        re.IGNORECASE,
    )
    if not date_match:
        return None
    fecha_text = date_match.group(0)
    try:
        if " de " in fecha_text.lower():
            return _parse_spanish_text_date(fecha_text, advertencias)
        return parse_date(fecha_text)
    except ValueError:
        advertencias.append(error_message)
        return None


def _extract_tipo_documento(text: str) -> str | None:
    value = _extract_labeled_text(text, "Tipo de Documento", ("Documento", "Fecha de Nacimiento"))
    return _normalize_doc_type(value)


def _extract_document_number(text: str) -> str | None:
    match = re.search(r"(?:^|\s)Documento\s*:?\s*(?P<documento>\d[\d., -]{3,})", text, re.IGNORECASE)
    if not match:
        return None
    return _clean_document(match.group("documento"))


def _label_pattern(label: str) -> str:
    words = [re.escape(word) for word in label.split()]
    return r"\b" + r"\s+".join(words) + r"\b"


def _field_value(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*:?\s*(?P<value>[A-ZÁÉÍÓÚÑ ]+)", text, re.IGNORECASE)
    if not match:
        return None
    value = " ".join(match.group("value").split())
    return value.title() if value else None


def _section_text(text: str, heading: str) -> str | None:
    pattern = re.compile(
        rf"{re.escape(heading)}\s*\n(?P<section>.*?)(?=\n[A-ZÁÉÍÓÚÑ ]{{5,}}\n|$)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    section = match.group("section").strip()
    return section or None


def _first_meaningful_section_line(section: str) -> str | None:
    for line in section.splitlines():
        value = " ".join(line.strip().split())
        if not value:
            continue
        if re.search(r"\b(?:NIT|FECHA|VIGENCIA)\b", value, re.IGNORECASE):
            continue
        return value.title()
    return None


def _extract_public_entity(text: str) -> str | None:
    match = _ENTITY_RE.search(text)
    if not match:
        return None
    return match.group("entity")


def _clean_public_entity_name(value: object) -> str | None:
    text = clean_cetil_value(value)
    if not text:
        return None
    split = re.split(
        r"\b(?:NIT|FECHA|VIGENCIA|EL\s+SISTEMA\s+GENERAL\s+DE\s+PENSIONES)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ ]+", " ", split)
    text = " ".join(text.split())
    if not text or "SISTEMA GENERAL DE PENSIONES" in text.upper():
        return None
    return text.upper()


def _clean_period_cargo(value: object) -> str | None:
    text = clean_cetil_value(value)
    if not text:
        return None
    text = re.sub(r"\b(?:CARGO|SI|SÍ|NO|NINGUNO|LABORAL|P[ÚU]BLICO|PRIVADO)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:MUNICIPIO|ALCALD[IÍ]A|GOBERNACI[ÓO]N|DEPARTAMENTO)\s+DE\b.*", " ", text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    return text.title() if text else None


def _extract_nit(text: str) -> str | None:
    match = re.search(r"\bNIT\b\s*:?\s*(?P<nit>\d[\d., -]{5,})(?:-\d)?", text, re.IGNORECASE)
    if not match:
        return None
    return re.sub(r"\D", "", match.group("nit"))


def _extract_vigencia_pensional(text: str, advertencias: list[str]) -> date | None:
    match = re.search(
        r"VIGENCIA\s+(?:DEL\s+)?SISTEMA\s+GENERAL\s+DE\s+PENSIONES\s*:?\s*"
        r"(?P<fecha>\d{2}[-/]\d{2}[-/]\d{4}|[A-Za-zÁÉÍÓÚÑáéíóúñ]+\s+\d{1,2}\s+de\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        fallback = re.search(
            r"\d{2}[-/]\d{2}[-/]\d{4}|[A-Za-zÁÉÍÓÚÑáéíóúñ]+\s+\d{1,2}\s+de\s+\d{4}",
            text,
            re.IGNORECASE,
        )
        if not fallback:
            return None
        fecha_text = fallback.group(0)
    else:
        fecha_text = match.group("fecha")
    try:
        if " de " in fecha_text.lower():
            return _parse_spanish_text_date(fecha_text, advertencias)
        return parse_date(fecha_text)
    except ValueError:
        advertencias.append("No fue posible normalizar la fecha de vigencia pensional detectada.")
        return None


def _build_nombre_completo(*parts: str | None) -> str | None:
    values = [part for part in parts if part]
    return " ".join(values) if values else None


def _normalize_doc_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^A-ZÁÉÍÓÚÑ]", " ", value.upper().replace(".", " "))
    normalized = " ".join(normalized.split())
    normalized = re.split(r"\bDOCUMENTO\b", normalized, maxsplit=1)[0].strip()
    token = normalized.split()[0] if normalized else ""
    if token in {"C", "CC", "CE", "TI", "PA"}:
        return token
    normalized = normalized.replace(" ", "")
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
