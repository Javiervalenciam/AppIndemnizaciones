from __future__ import annotations

import re
import unicodedata
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
    ExtractionIssue,
    ExtractionIssueCode,
    ExtractionIssueLog,
    IssueSeverity,
)
from app_indemnizaciones.services.cetil_ocr import (
    OCR_FAILED,
    OCR_NO_TEXT,
    OCR_UNAVAILABLE,
    ocr_pdf_pages,
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

# Conceptos salariales canónicos y sus variantes en distintos CETIL.
# La comparación ignora tildes, mayúsculas, puntos y espacios repetidos.
SALARY_CONCEPT_ASIGNACION = "ASIGNACIÓN BÁSICA MENSUAL"
SALARY_CONCEPT_TOTAL_DEVENGADO = "Total Devengado"
_SALARY_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    SALARY_CONCEPT_ASIGNACION: (
        "ASIGNACION BASICA MENSUAL",
        "ASIGNACION BASICA",
        "SUELDO BASICO MENSUAL",
        "SUELDO BASICO",
    ),
    SALARY_CONCEPT_TOTAL_DEVENGADO: (
        "TOTAL DEVENGADO",
        "TOTAL DEVENGADO MENSUAL",
    ),
}
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

MAX_PDF_PAGES = 200


@dataclass(frozen=True)
class PdfReadResult:
    """Contenido leído del PDF y el lector que lo produjo."""

    pages: dict[int, str]
    tables_by_page: dict[int, list[list[list[str | None]]]]
    reader: str

    @property
    def page_count(self) -> int:
        return len(self.pages)


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
        read_result = self._read_pdf(content)
        pages = read_result.pages
        ocr_applied = False
        ocr_error_code: str | None = None
        ocr_error_detail: str | None = None

        if not any(text.strip() for text in pages.values()):
            attempt = ocr_pdf_pages(content)
            if any(text.strip() for text in attempt.pages.values()):
                pages = attempt.pages
                ocr_applied = True
            elif attempt.error_code:
                ocr_error_code = attempt.error_code
                ocr_error_detail = attempt.detail

        return self.extract_from_pages(
            pages,
            tables_by_page=read_result.tables_by_page,
            ocr_applied=ocr_applied,
            ocr_error_code=ocr_error_code,
            ocr_error_detail=ocr_error_detail,
        )

    def extract_from_pages(
        self,
        pages: dict[int, str],
        tables_by_page: dict[int, list[list[list[str | None]]]] | None = None,
        *,
        ocr_applied: bool = False,
        ocr_error_code: str | None = None,
        ocr_error_detail: str | None = None,
    ) -> CetilExtractionResult:
        text_pages = {page: text or "" for page, text in pages.items()}
        full_text = "\n".join(text_pages.values())
        log = ExtractionIssueLog()

        if ocr_applied:
            log.add(
                code=ExtractionIssueCode.OCR_APPLIED_REVIEW_REQUIRED,
                severity=IssueSeverity.REVIEW_REQUIRED,
                message=(
                    "El texto del CETIL se obtuvo mediante OCR porque el PDF no tenía "
                    "capa de texto; puede contener errores de reconocimiento."
                ),
                field="documento",
                locator="capa de texto",
                cause="El PDF original es una imagen escaneada.",
                action=(
                    "Compare cada nombre, fecha, periodo y valor salarial con el PDF "
                    "original antes de calcular."
                ),
            )

        if not full_text.strip():
            log.add(**_empty_text_issue(ocr_error_code, ocr_error_detail))
            return CetilExtractionResult(
                advertencias=log.warnings,
                issues=log.issues,
                texto_paginas=text_pages,
                confidence_score=0.0,
            )

        for page_number, page_text in text_pages.items():
            if page_text.strip():
                continue
            log.add(
                code=ExtractionIssueCode.PDF_PAGE_WITHOUT_TEXT,
                severity=IssueSeverity.WARNING,
                message=f"La página {page_number} no contiene texto legible.",
                field="documento",
                page=page_number,
                action="Verifique en el PDF si esa página es una imagen o está en blanco.",
            )

        metadata = self._extract_metadata(full_text, log)
        trabajador = self._extract_trabajador(full_text, log)
        entidad_certificadora = self._extract_entidad_certificadora(full_text)
        entidad_empleadora = self._extract_entidad_empleadora(full_text, log)
        periodos = self._extract_periodos(text_pages, log, tables_by_page=tables_by_page)
        factores = self._extract_factores(text_pages, log)
        factores = _apply_ibl_sugerido(factores, log)

        if not periodos:
            log.add(
                code=ExtractionIssueCode.PERIODS_MISSING,
                severity=IssueSeverity.ERROR,
                message="No se detectaron periodos certificados.",
                field="periodos_certificados",
                locator="PERIODOS CERTIFICADOS",
                action=(
                    "Verifique que el CETIL conserve la tabla de periodos. "
                    "Si la tabla está partida o sin encabezado, regístrela manualmente."
                ),
            )
        if not factores:
            log.add(
                code=ExtractionIssueCode.SALARY_BLOCKS_MISSING,
                severity=IssueSeverity.ERROR,
                message="No se detectaron bloques de factores salariales.",
                field="factores_salariales",
                locator="FACTORES SALARIALES",
                action="Revise que el CETIL incluya la tabla salarial por año.",
            )
        if periodos and not factores:
            log.add(
                code=ExtractionIssueCode.SALARY_BLOCKS_MISSING,
                severity=IssueSeverity.REVIEW_REQUIRED,
                message=(
                    "Se detectaron periodos, pero no se detectaron factores salariales. "
                    "Revise manualmente la tabla antes de calcular."
                ),
                field="factores_salariales",
                action="Ingrese el IBL de cada año manualmente en el cuadro de liquidación.",
            )

        confidence = self._confidence_score(periodos, factores, log.issues)
        result = CetilExtractionResult(
            metadata=metadata,
            trabajador=trabajador,
            entidad_empleadora=entidad_empleadora,
            entidad_certificadora=entidad_certificadora,
            periodos_certificados=periodos,
            factores_salariales=factores,
            advertencias=log.warnings,
            issues=log.issues,
            texto_paginas=text_pages,
            confidence_score=confidence,
        )
        filas, annual_warnings = normalize_cetil_to_annual_periods(result, log=log)
        return replace(
            result,
            filas_liquidables_anuales=filas,
            advertencias=log.warnings,
            issues=log.issues,
            confidence_score=self._confidence_score(periodos, factores, log.issues),
        )

    @staticmethod
    def _read_pdf(content: bytes) -> PdfReadResult:
        """Lee el PDF con pdfplumber y cae a PyMuPDF si el primero falla.

        El objetivo es no rechazar un PDF legible solo porque un lector no
        soporte su estructura. Cada causa se traduce a un mensaje accionable.
        """
        failures: list[tuple[str, Exception]] = []

        if pdfplumber is not None:
            try:
                with pdfplumber.open(BytesIO(content)) as pdf:
                    _ensure_page_limit(len(pdf.pages))
                    text_pages: dict[int, str] = {}
                    tables_by_page: dict[int, list[list[list[str | None]]]] = {}
                    for page_number, page in enumerate(pdf.pages, start=1):
                        text_pages[page_number] = (
                            page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                        )
                        tables_by_page[page_number] = page.extract_tables() or []
                    return PdfReadResult(
                        pages=text_pages,
                        tables_by_page=tables_by_page,
                        reader="pdfplumber",
                    )
            except CetilExtractionError:
                raise
            except Exception as exc:  # noqa: BLE001 - se reintenta con otro lector
                failures.append(("pdfplumber", exc))

        try:
            with fitz.open(stream=content, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise CetilExtractionError(
                        "El PDF CETIL está protegido con contraseña. "
                        "Descárguelo sin cifrado y vuelva a intentarlo."
                    )
                _ensure_page_limit(doc.page_count)
                pages: dict[int, str] = {}
                for page_number, page in enumerate(doc, start=1):
                    pages[page_number] = page.get_text("text")
                return PdfReadResult(pages=pages, tables_by_page={}, reader="pymupdf")
        except CetilExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 - se reporta la causa agregada
            failures.append(("pymupdf", exc))

        raise CetilExtractionError(_describe_read_failure(failures))

    @staticmethod
    def _extract_section_value(text: str, heading: str) -> str | None:
        pattern = re.compile(rf"{re.escape(heading)}\s*\n(?P<value>.+)", re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return None
        value = match.group("value").strip()
        return value[:180] or None

    def _extract_entidad_certificadora(self, text: str) -> str | None:
        """Devuelve solo el nombre, sin las etiquetas ``Nombre:`` / ``Nit:``."""
        section = _block_between(
            text,
            "DATOS DE LA ENTIDAD CERTIFICADORA",
            (
                "DATOS DEL EMPLEADO",
                "DATOS DE LA ENTIDAD EMPLEADORA",
                "PERIODOS CERTIFICADOS",
            ),
        )
        if not section:
            return None
        for line in section.splitlines():
            normalized = " ".join(line.split())
            if not normalized:
                continue
            value = _extract_labeled_text(normalized, "Nombre", ("Nit",)) or normalized
            cleaned = _clean_public_entity_name(value)
            if cleaned:
                return cleaned
        return None

    def _extract_metadata(self, text: str, log: ExtractionIssueLog) -> CetilMetadata:
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
            fecha_expedicion = _parse_spanish_text_date(
                expedition_match.group("fecha"),
                log,
                field="metadata.fecha_expedicion_cetil",
            )
        if not numero_match:
            log.add(
                code=ExtractionIssueCode.METADATA_MISSING,
                severity=IssueSeverity.WARNING,
                message="No se detectó el número del CETIL.",
                field="metadata.numero_cetil",
                action="Verifique el encabezado del certificado o ingréselo manualmente.",
            )
        if not expedition_match:
            log.add(
                code=ExtractionIssueCode.METADATA_MISSING,
                severity=IssueSeverity.WARNING,
                message="No se detectó la ciudad y fecha de expedición del CETIL.",
                field="metadata.fecha_expedicion_cetil",
                action="Verifique el encabezado del certificado antes de exportar.",
            )

        return CetilMetadata(
            numero_cetil=numero_match.group("numero") if numero_match else None,
            ciudad_expedicion=expedition_match.group("ciudad").strip().upper()
            if expedition_match
            else None,
            fecha_expedicion_cetil=fecha_expedicion,
        )

    def _extract_trabajador(self, text: str, log: ExtractionIssueLog) -> CetilTrabajador | None:
        employee_block = _block_between(text, "DATOS DEL EMPLEADO", ("PERIODOS CERTIFICADOS",))
        search_text = employee_block or text

        documento = _extract_document_number(search_text)
        tipo_documento = _extract_tipo_documento(search_text)
        fecha_nacimiento = _extract_labeled_date(
            search_text,
            "Fecha de Nacimiento",
            log,
            error_message="No fue posible normalizar la fecha de nacimiento detectada.",
            field="trabajador.fecha_nacimiento",
        )
        genero = (
            _extract_labeled_text(search_text, "GÉNERO", _PERSON_LABELS)
            or _extract_labeled_text(search_text, "GENERO", _PERSON_LABELS)
            or _extract_labeled_text(search_text, "SEXO", _PERSON_LABELS)
        )
        if not genero:
            log.add(
                code=ExtractionIssueCode.WORKER_GENDER_MISSING,
                severity=IssueSeverity.WARNING,
                message="No se detectó campo explícito de género en el CETIL.",
                field="trabajador.genero",
                action="Confirme el género manualmente si el cálculo lo requiere.",
            )

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
            log.add(
                code=ExtractionIssueCode.WORKER_DATA_MISSING,
                severity=IssueSeverity.REVIEW_REQUIRED,
                message="No se detectaron datos básicos del trabajador con alta confianza.",
                field="trabajador",
                locator="DATOS DEL EMPLEADO",
                action="Verifique manualmente la identificación del trabajador en el PDF.",
            )
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
        log: ExtractionIssueLog,
    ) -> CetilEntidadEmpleadora | None:
        section = _block_between(
            text,
            "DATOS DE LA ENTIDAD EMPLEADORA",
            ("DATOS DEL EMPLEADO", "PERIODOS CERTIFICADOS"),
        )
        if not section:
            log.add(
                code=ExtractionIssueCode.ENTITY_SECTION_MISSING,
                severity=IssueSeverity.ERROR,
                message="No se detectó sección de entidad empleadora en el CETIL.",
                field="entidad_empleadora",
                locator="DATOS DE LA ENTIDAD EMPLEADORA",
                action="Verifique que el PDF conserve la sección de la entidad empleadora.",
            )
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
        fecha_vigencia = _extract_vigencia_pensional(section, log)

        if not nombre:
            log.add(
                code=ExtractionIssueCode.ENTITY_NAME_MISSING,
                severity=IssueSeverity.ERROR,
                message="No se detectó nombre de entidad empleadora.",
                field="entidad_empleadora.nombre",
                action="Escriba el nombre de la entidad antes de exportar.",
            )
        if not nit:
            log.add(
                code=ExtractionIssueCode.ENTITY_NIT_MISSING,
                severity=IssueSeverity.WARNING,
                message="No se detectó NIT de entidad empleadora.",
                field="entidad_empleadora.nit",
                action="Confirme el NIT manualmente en el certificado.",
            )

        return CetilEntidadEmpleadora(
            nombre_entidad_empleadora=nombre,
            nit_entidad_empleadora=nit,
            fecha_vigencia_sistema_general_pensiones=fecha_vigencia,
        )

    def _extract_periodos(
        self,
        pages: dict[int, str],
        log: ExtractionIssueLog,
        tables_by_page: dict[int, list[list[list[str | None]]]] | None = None,
    ) -> list[CetilPeriodoCertificado]:
        tables = tables_by_page or {}
        periodos = _extract_periodos_from_tables(tables, log)
        pages_with_tables = _pages_with_period_tables(tables)

        for page_number, text in pages.items():
            if page_number in pages_with_tables:
                # La tabla ya aportó los periodos de esta página; el texto
                # duplicaría la misma información con menos columnas.
                continue
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
                    log.add(
                        code=ExtractionIssueCode.PERIODS_TABLE_ROW_INVALID,
                        severity=IssueSeverity.ERROR,
                        message=f"No fue posible normalizar un periodo en página {page_number}.",
                        field="periodos_certificados",
                        page=page_number,
                        cause="La fila no contiene dos fechas válidas en formato DD-MM-AAAA.",
                        action="Corrija las fechas del periodo manualmente en la tabla.",
                    )
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
                        dias_interrupcion=parsed_remainder["total_no_dias"],
                        fuente_pagina=page_number,
                        raw_text=line,
                    )
                )
        return _dedupe_periodos(periodos)

    def _extract_factores(
        self,
        pages: dict[int, str],
        log: ExtractionIssueLog,
    ) -> list[CetilFactorSalarial]:
        factores: list[CetilFactorSalarial] = []
        salary_blocks = extract_salary_blocks_across_pages(pages)
        for salary_block in salary_blocks:
            for warning in salary_block.warnings:
                log.add(
                    code=ExtractionIssueCode.SALARY_BLOCK_SPLIT_PAGES,
                    severity=IssueSeverity.INFO,
                    message=warning,
                    field=f"factores_salariales.{salary_block.anio}",
                    page=salary_block.start_page,
                    locator=f"FACTORES SALARIALES {salary_block.anio}",
                )
            block_has_values = False
            for concepto in (SALARY_CONCEPT_ASIGNACION, SALARY_CONCEPT_TOTAL_DEVENGADO):
                raw_line = _concept_context(salary_block.raw_text, concepto)
                if not raw_line:
                    continue
                values = _money_values(raw_line)
                monthly_values = _monthly_values(values, log, salary_block.anio, concepto)
                selected_value = _select_suggested_value(values)
                c_ibc_mensual = _monthly_ibc_flags(raw_line)
                is_total_devengado = concepto == SALARY_CONCEPT_TOTAL_DEVENGADO
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
                        c_ibc_mensual=c_ibc_mensual,
                        fuente_pagina=salary_block.start_page,
                        raw_text=raw_line,
                    )
                )
                if any(value > 0 for value in values):
                    block_has_values = True
            if not block_has_values:
                log.add(
                    code=ExtractionIssueCode.SALARY_YEAR_WITHOUT_VALUES,
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    message=(
                        f"No se detectaron valores salariales positivos para el año {salary_block.anio}."
                    ),
                    field=f"factores_salariales.{salary_block.anio}",
                    page=salary_block.start_page,
                    locator=f"FACTORES SALARIALES {salary_block.anio}",
                    action="Ingrese el IBL de ese año manualmente en el cuadro de liquidación.",
                )
        return factores

    @staticmethod
    def _confidence_score(
        periodos: list[CetilPeriodoCertificado],
        factores: list[CetilFactorSalarial],
        issues: list[ExtractionIssue] | None = None,
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
        score = min(score, 1.0)

        # La confianza debe reflejar las incidencias, no solo la presencia de datos.
        penalties = {
            IssueSeverity.ERROR: 0.30,
            IssueSeverity.REVIEW_REQUIRED: 0.12,
            IssueSeverity.WARNING: 0.03,
        }
        for issue in issues or []:
            if issue.severity is IssueSeverity.BLOCK:
                return 0.0
            score -= penalties.get(issue.severity, 0.0)
        return round(max(score, 0.0), 2)


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
        # Si la entidad se detectó sin la etiqueta previa, el cargo aún puede
        # arrastrar "ENTIDAD RESPONSABLE:". No es parte del cargo.
        cargo_source = re.sub(
            r"\bENTIDAD\s+RESPONSABLE\b\s*:?\s*$",
            "",
            cargo_source,
            flags=re.IGNORECASE,
        ).strip()
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
    log: ExtractionIssueLog,
) -> list[CetilPeriodoCertificado]:
    periodos: list[CetilPeriodoCertificado] = []
    for page_number, tables in tables_by_page.items():
        for table in tables:
            header_index = _period_header_index(table)
            if header_index is None:
                continue
            columns = _map_period_columns(table[header_index])
            if "desde" not in columns or "hasta" not in columns:
                continue
            for row_number, row in enumerate(table[header_index + 1 :], start=header_index + 1):
                if not row or not any(clean_cetil_value(value) for value in row):
                    continue
                raw_desde = _cell(row, columns.get("desde"))
                raw_hasta = _cell(row, columns.get("hasta"))
                if not raw_desde or not raw_hasta:
                    continue
                try:
                    fecha_desde = parse_date(raw_desde)
                    fecha_hasta = parse_date(raw_hasta)
                except ValueError:
                    log.add(
                        code=ExtractionIssueCode.PERIODS_TABLE_ROW_INVALID,
                        severity=IssueSeverity.ERROR,
                        message=f"No fue posible normalizar un periodo en página {page_number}.",
                        field="periodos_certificados",
                        page=page_number,
                        locator=f"tabla de periodos, fila {row_number + 1}",
                        cause="La fila no contiene dos fechas válidas en formato DD-MM-AAAA.",
                        action="Corrija las fechas del periodo manualmente en la tabla.",
                    )
                    continue

                dias_interrupcion = _parse_int_cell(
                    _cell(row, columns.get("dias_interrupcion"))
                )
                periodos.append(
                    CetilPeriodoCertificado(
                        fecha_desde=fecha_desde,
                        fecha_hasta=fecha_hasta,
                        tipo_vinculacion=clean_cetil_value(
                            _cell(row, columns.get("tipo_vinculacion"))
                        ),
                        tipo_empleado=clean_cetil_value(
                            _cell(row, columns.get("tipo_empleado"))
                        ),
                        cargo=_clean_period_cargo(_cell(row, columns.get("cargo"))),
                        aportes_pension=clean_cetil_value(
                            _cell(row, columns.get("aportes_pension"))
                        ),
                        aportes_salud=clean_cetil_value(
                            _cell(row, columns.get("aportes_salud"))
                        ),
                        aportes_riesgos=clean_cetil_value(
                            _cell(row, columns.get("aportes_riesgos"))
                        ),
                        fondo_aporte=clean_cetil_value(
                            _cell(row, columns.get("fondo_aporte"))
                        ),
                        entidad_responsable=_clean_public_entity_name(
                            _cell(row, columns.get("entidad_responsable"))
                        ),
                        total_no_dias=dias_interrupcion,
                        dias_interrupcion=dias_interrupcion,
                        cargo_alto_riesgo=clean_cetil_value(
                            _cell(row, columns.get("cargo_alto_riesgo"))
                        ),
                        tiempo_completo=clean_cetil_value(
                            _cell(row, columns.get("tiempo_completo"))
                        ),
                        horas_semanales_laboradas=clean_cetil_value(
                            _cell(row, columns.get("horas_semanales_laboradas"))
                        ),
                        fuente_pagina=page_number,
                        raw_text=" | ".join(clean_cetil_value(value) or "" for value in row),
                    )
                )
    return periodos


def _looks_like_period_table(table: list[list[str | None]]) -> bool:
    return _period_header_index(table) is not None


def _pages_with_period_tables(
    tables_by_page: dict[int, list[list[list[str | None]]]],
) -> set[int]:
    return {
        page_number
        for page_number, tables in tables_by_page.items()
        if any(_looks_like_period_table(table) for table in tables)
    }


def _period_header_index(table: list[list[str | None]]) -> int | None:
    """Ubica la fila de encabezado real de la tabla de periodos.

    Los CETIL varían en el número de filas de título y subtítulo; por eso se
    busca la fila que contiene DESDE y HASTA en lugar de asumir `table[1]`.
    """
    for index, row in enumerate(table):
        cells = [_normalize_header(value) for value in row]
        joined = " ".join(cells)
        if "DESDE" in joined and "HASTA" in joined:
            return index
    return None


def _map_period_columns(header_row: list[str | None]) -> dict[str, int]:
    """Mapea campos por nombre de columna, nunca por posición fija."""
    columns: dict[str, int] = {}
    for index, raw in enumerate(header_row):
        header = _normalize_header(raw)
        if not header:
            continue
        if "DESDE" in header and "desde" not in columns:
            columns["desde"] = index
        elif "HASTA" in header and "hasta" not in columns:
            columns["hasta"] = index
        elif "VINCULACION" in header and "tipo_vinculacion" not in columns:
            columns["tipo_vinculacion"] = index
        elif "TIPO DE EMPLEADO" in header and "tipo_empleado" not in columns:
            columns["tipo_empleado"] = index
        elif "ALTO RIESGO" in header and "cargo_alto_riesgo" not in columns:
            columns["cargo_alto_riesgo"] = index
        elif header.startswith("CARGO") and "cargo" not in columns:
            columns["cargo"] = index
        elif "PENSION" in header and "aportes_pension" not in columns:
            columns["aportes_pension"] = index
        elif "SALUD" in header and "aportes_salud" not in columns:
            columns["aportes_salud"] = index
        elif "RIESGO" in header and "aportes_riesgos" not in columns:
            columns["aportes_riesgos"] = index
        elif "FONDO" in header and "fondo_aporte" not in columns:
            columns["fondo_aporte"] = index
        elif "ENTIDAD RESPONSABLE" in header and "entidad_responsable" not in columns:
            columns["entidad_responsable"] = index
        elif (
            "INTERRUPCION" in header or ("DIA" in header and "NO" in header)
        ) and "dias_interrupcion" not in columns:
            columns["dias_interrupcion"] = index
        elif "TIEMPO COMPLETO" in header and "tiempo_completo" not in columns:
            columns["tiempo_completo"] = index
        elif "HORAS" in header and "horas_semanales_laboradas" not in columns:
            columns["horas_semanales_laboradas"] = index
    return columns


def _strip_accents(text: str) -> str:
    """Quita tildes/diéresis sin alterar mayúsculas ni espacios internos."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _normalize_header(value: object) -> str:
    text = clean_cetil_value(value) or ""
    return " ".join(_strip_accents(text).upper().split())


def _cell(row: list[str | None], index: int | None) -> str | None:
    if index is None or index < 0 or index >= len(row):
        return None
    return row[index]


def _parse_int_cell(value: object) -> int | None:
    text = clean_cetil_value(value)
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _dedupe_periodos(
    periodos: list[CetilPeriodoCertificado],
) -> list[CetilPeriodoCertificado]:
    """Fusiona periodos descritos por la tabla y por el texto de la página.

    La tabla y el texto pueden aportar columnas distintas del mismo periodo. Se
    conserva una sola fila por rango/cargo/entidad y se completan los campos que
    falten en la primera descripción. Rangos distintos nunca se fusionan.
    """
    result: list[CetilPeriodoCertificado] = []
    index_by_key: dict[tuple[object, ...], int] = {}

    for periodo in periodos:
        key = (
            periodo.fecha_desde,
            periodo.fecha_hasta,
            _normalize_header(periodo.cargo),
            _normalize_header(periodo.entidad_responsable),
        )
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(result)
            result.append(periodo)
            continue

        existing = result[existing_index]
        merged = replace(
            existing,
            tipo_vinculacion=existing.tipo_vinculacion or periodo.tipo_vinculacion,
            tipo_empleado=existing.tipo_empleado or periodo.tipo_empleado,
            aportes_pension=existing.aportes_pension or periodo.aportes_pension,
            aportes_salud=existing.aportes_salud or periodo.aportes_salud,
            aportes_riesgos=existing.aportes_riesgos or periodo.aportes_riesgos,
            fondo_aporte=existing.fondo_aporte or periodo.fondo_aporte,
            dias_interrupcion=(
                existing.dias_interrupcion
                if existing.dias_interrupcion is not None
                else periodo.dias_interrupcion
            ),
            total_no_dias=(
                existing.total_no_dias
                if existing.total_no_dias is not None
                else periodo.total_no_dias
            ),
            cargo_alto_riesgo=existing.cargo_alto_riesgo or periodo.cargo_alto_riesgo,
            tiempo_completo=existing.tiempo_completo or periodo.tiempo_completo,
            horas_semanales_laboradas=(
                existing.horas_semanales_laboradas or periodo.horas_semanales_laboradas
            ),
        )
        result[existing_index] = merged
    return result


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


def _normalize_concept(text: str) -> str:
    """Normaliza un concepto salarial para comparar variantes del CETIL."""
    return _normalize_header(text).replace(".", "").replace(":", "").strip()


def _concept_aliases(concept: str) -> tuple[str, ...]:
    return _SALARY_CONCEPT_ALIASES.get(concept, (_normalize_concept(concept),))


def _concept_context(block: str, concept: str) -> str | None:
    """Devuelve la línea del concepto con sus continuaciones monetarias.

    La búsqueda es tolerante a tildes, puntos, mayúsculas y variantes del
    nombre. Se detiene al llegar a otro concepto conocido o a un nuevo año.
    """
    aliases = _concept_aliases(concept)
    other_aliases = tuple(
        alias
        for other, values in _SALARY_CONCEPT_ALIASES.items()
        if other != concept
        for alias in values
    )
    lines = block.splitlines()
    for index, line in enumerate(lines):
        normalized_line = _normalize_concept(line)
        if not any(alias in normalized_line for alias in aliases):
            continue
        # Las notas al pie ("C.IBC: Indica si el factor...") no traen montos.
        if not _MONEY_RE.search(line):
            continue
        context = [line.strip()]
        for following in lines[index + 1 : index + 4]:
            if _FACTOR_HEADER_RE.search(following):
                break
            normalized_following = _normalize_concept(following)
            if any(alias in normalized_following for alias in other_aliases):
                break
            context.append(following.strip())
            if len(_MONEY_RE.findall(" ".join(context))) >= 12:
                break
        return " ".join(part for part in context if part)
    return None


def _monthly_ibc_flags(text: str) -> dict[str, bool | None]:
    """Asocia cada valor mensual con la marca C.IBC (S/N) que le sigue.

    El CETIL imprime ``3,150.00 S`` para indicar que el factor hace parte del
    IBC en ese mes. Si no hay marca, el mes queda en ``None`` (sin dato), nunca
    en ``False``: no se debe inventar una exclusión.
    """
    flags: dict[str, bool | None] = {}
    for index, match in enumerate(_MONEY_RE.finditer(text)):
        if index >= len(MESES):
            break
        tail = text[match.end() : match.end() + 8]
        flag_match = re.match(r"\s*(?P<flag>[SN])\b", tail, re.IGNORECASE)
        flags[MESES[index]] = None if flag_match is None else flag_match.group("flag").upper() == "S"
    for month in MESES:
        flags.setdefault(month, None)
    return flags


def _monthly_values(
    values: list[Decimal],
    log: ExtractionIssueLog,
    anio: int,
    concepto: str,
) -> dict[str, Decimal | None]:
    if len(values) != 12:
        log.add(
            code=ExtractionIssueCode.SALARY_MONTHS_INCOMPLETE,
            severity=IssueSeverity.REVIEW_REQUIRED,
            message=(
                "No fue posible asociar todos los valores salariales a meses con alta confianza "
                f"para {concepto} {anio}."
            ),
            field=f"factores_salariales.{anio}",
            locator=f"FACTORES SALARIALES {anio}",
            cause=f"Se esperaban 12 valores mensuales y se detectaron {len(values)}.",
            action="Confirme los valores mensuales del año antes de calcular.",
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


@dataclass(frozen=True)
class IblSelection:
    """Resultado explícito de elegir el IBL de un año."""

    value: Decimal | None
    metodo: str | None
    evidencia: str | None
    requiere_revision: bool


def _apply_ibl_sugerido(
    factores: list[CetilFactorSalarial],
    log: ExtractionIssueLog,
) -> list[CetilFactorSalarial]:
    by_year: dict[int, list[CetilFactorSalarial]] = {}
    for factor in factores:
        by_year.setdefault(factor.anio, []).append(factor)

    selected_by_year: dict[int, IblSelection] = {}
    for anio, year_factors in by_year.items():
        assignment = _find_factor(year_factors, SALARY_CONCEPT_ASIGNACION)
        total = _find_factor(year_factors, SALARY_CONCEPT_TOTAL_DEVENGADO)
        # Si la asignación básica existe con valores, un empate es una
        # ambigüedad real: no se oculta cayendo al Total Devengado.
        prefer_assignment = assignment is not None and any(
            value > 0 for value in assignment.valores_encontrados
        )
        if prefer_assignment:
            selection = _select_ibl_from_factor(
                assignment,
                anio,
                SALARY_CONCEPT_ASIGNACION,
                "asignacion_basica_mensual",
                log,
            )
        else:
            selection = _select_ibl_from_factor(
                total,
                anio,
                SALARY_CONCEPT_TOTAL_DEVENGADO,
                "total_devengado",
                log,
            )
        if selection.value is None:
            log.add(
                code=ExtractionIssueCode.IBL_MANUAL_REQUIRED,
                severity=IssueSeverity.REVIEW_REQUIRED,
                message=f"No se detectó IBL para el año {anio}. Debe ingresarse manualmente.",
                field=f"filas_liquidables_anuales.{anio}.ibl",
                locator=f"FACTORES SALARIALES {anio}",
                action="Escriba el IBL del año en el cuadro de liquidación antes de calcular.",
            )
            selection = IblSelection(
                value=None,
                metodo="manual",
                evidencia="No se detectó un valor salarial utilizable.",
                requiere_revision=True,
            )
        selected_by_year[anio] = selection

    return [
        replace(
            factor,
            ibl_sugerido=selected_by_year[factor.anio].value,
            ibl_metodo=selected_by_year[factor.anio].metodo,
            ibl_evidencia=selected_by_year[factor.anio].evidencia,
            ibl_requiere_revision=selected_by_year[factor.anio].requiere_revision,
        )
        for factor in factores
    ]


def _select_ibl_from_factor(
    factor: CetilFactorSalarial | None,
    anio: int,
    label: str,
    metodo: str,
    log: ExtractionIssueLog,
) -> IblSelection:
    if factor is None:
        return IblSelection(value=None, metodo=None, evidencia=None, requiere_revision=False)

    positive_values = [value for value in factor.valores_encontrados if value > 0]
    if not positive_values:
        return IblSelection(value=None, metodo=None, evidencia=None, requiere_revision=False)

    counts = Counter(positive_values)
    most_common = counts.most_common()
    top_count = most_common[0][1]
    tied = [value for value, count in most_common if count == top_count]
    if len(tied) > 1:
        log.add(
            code=ExtractionIssueCode.IBL_AMBIGUOUS,
            severity=IssueSeverity.REVIEW_REQUIRED,
            message=(
                f"No se detectó IBL confiable para el año {anio}; empate entre valores de {label}."
            ),
            field=f"filas_liquidables_anuales.{anio}.ibl",
            page=factor.fuente_pagina,
            locator=f"FACTORES SALARIALES {anio}",
            cause="Dos o más valores salariales aparecen con la misma frecuencia.",
            action="Seleccione manualmente el IBL que corresponda al periodo certificado.",
        )
        return IblSelection(
            value=None,
            metodo="manual",
            evidencia=f"Empate entre {len(tied)} valores de {label}.",
            requiere_revision=True,
        )

    requiere_revision = len(set(positive_values)) > 1
    if requiere_revision:
        log.add(
            code=ExtractionIssueCode.IBL_ATYPICAL,
            severity=IssueSeverity.WARNING,
            message=(
                f"IBL sugerido por valor positivo más frecuente en el año {anio}; "
                "se detectó posible valor atípico y debe revisarse manualmente."
            ),
            field=f"filas_liquidables_anuales.{anio}.ibl",
            page=factor.fuente_pagina,
            locator=f"FACTORES SALARIALES {anio}",
            action="Confirme que el valor más frecuente sea el IBL correcto del año.",
        )

    meses_ibc = [month for month, flag in factor.c_ibc_mensual.items() if flag is True]
    meses_no_ibc = [month for month, flag in factor.c_ibc_mensual.items() if flag is False]
    meses_no_ibc_con_valor = [
        month
        for month in meses_no_ibc
        if (factor.valores_mensuales.get(month) or Decimal("0")) > 0
    ]
    evidencia = (
        f"{label}: valor más frecuente {tied[0]} "
        f"({top_count} de {len(positive_values)} valores mensuales positivos)."
    )
    if meses_ibc or meses_no_ibc:
        evidencia += (
            f" C.IBC marca {len(meses_ibc)} mes(es) dentro del IBC"
            f" y {len(meses_no_ibc)} fuera."
        )
        if meses_no_ibc_con_valor:
            # Un único IBL anual no representa meses con salario excluido del
            # IBC; requiere decisión sobre la ponderación mensual (ver D1).
            evidencia += (
                " Meses con salario fuera del IBC: "
                + ", ".join(meses_no_ibc_con_valor)
                + "."
            )
            requiere_revision = True

    return IblSelection(
        value=tied[0],
        metodo=metodo,
        evidencia=evidencia,
        requiere_revision=requiere_revision,
    )


def _find_factor(
    factores: list[CetilFactorSalarial],
    concept: str,
) -> CetilFactorSalarial | None:
    target = _normalize_concept(concept)
    for factor in factores:
        if _normalize_concept(factor.concepto) == target:
            return factor
    return None


def _parse_spanish_text_date(
    text: str,
    log: ExtractionIssueLog,
    *,
    field: str = "documento",
) -> date | None:
    match = re.search(
        r"(?P<month>[A-Za-zÁÉÍÓÚÑáéíóúñ]+)\s+(?P<day>\d{1,2})\s+de\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        log.add(
            code=ExtractionIssueCode.DOCUMENT_DATE_UNPARSEABLE,
            severity=IssueSeverity.WARNING,
            message="No fue posible normalizar una fecha en texto del certificado.",
            field=field,
            cause="La fecha no usa el patrón '<mes> <día> de <año>'.",
            action="Verifique la fecha en el PDF o ingrésela manualmente.",
        )
        return None

    month = _SPANISH_MONTHS.get(match.group("month").lower())
    if month is None:
        log.add(
            code=ExtractionIssueCode.DOCUMENT_DATE_UNPARSEABLE,
            severity=IssueSeverity.WARNING,
            message="No fue posible reconocer el mes en una fecha del certificado.",
            field=field,
            cause=f"El mes {match.group('month')!r} no está en el catálogo en español.",
            action="Verifique la fecha en el PDF o ingrésela manualmente.",
        )
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
    log: ExtractionIssueLog,
    *,
    error_message: str,
    field: str = "documento",
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
            return _parse_spanish_text_date(fecha_text, log, field=field)
        return parse_date(fecha_text)
    except ValueError:
        log.add(
            code=ExtractionIssueCode.DOCUMENT_DATE_UNPARSEABLE,
            severity=IssueSeverity.WARNING,
            message=error_message,
            field=field,
            cause="La fecha detectada no es una fecha calendario válida.",
            action="Corrija la fecha manualmente antes de calcular.",
        )
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
    if not text:
        return None
    # "Secretario (a)" no debe convertirse en "Secretario (A)".
    titled = text.title()
    return re.sub(r"\(([A-Z])\)", lambda match: f"({match.group(1).lower()})", titled)


def _extract_nit(text: str) -> str | None:
    match = re.search(r"\bNIT\b\s*:?\s*(?P<nit>\d[\d., -]{5,})(?:-\d)?", text, re.IGNORECASE)
    if not match:
        return None
    return re.sub(r"\D", "", match.group("nit"))


def _extract_vigencia_pensional(text: str, log: ExtractionIssueLog) -> date | None:
    match = re.search(
        r"VIGENCIA\s+(?:DEL\s+)?SISTEMA\s+GENERAL\s+DE\s+PENSIONES\s*:?\s*"
        r"(?P<fecha>\d{2}[-/]\d{2}[-/]\d{4}|[A-Za-zÁÉÍÓÚÑáéíóúñ]+\s+\d{1,2}\s+de\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        # No se usa la primera fecha de la sección como aproximación: eso
        # inventaba una vigencia a partir de la fecha de expedición.
        log.add(
            code=ExtractionIssueCode.METADATA_MISSING,
            severity=IssueSeverity.INFO,
            message="No se detectó fecha de vigencia del Sistema General de Pensiones.",
            field="entidad_empleadora.vigencia",
            locator="DATOS DE LA ENTIDAD EMPLEADORA",
            action="Revise la sección de la entidad si necesita ese dato para el expediente.",
        )
        return None

    fecha_text = match.group("fecha")
    try:
        if " de " in fecha_text.lower():
            return _parse_spanish_text_date(
                fecha_text, log, field="entidad_empleadora.vigencia"
            )
        return parse_date(fecha_text)
    except ValueError:
        log.add(
            code=ExtractionIssueCode.DOCUMENT_DATE_UNPARSEABLE,
            severity=IssueSeverity.WARNING,
            message="No fue posible normalizar la fecha de vigencia pensional detectada.",
            field="entidad_empleadora.vigencia",
            cause="La fecha detectada no es una fecha calendario válida.",
            action="Corrija la fecha manualmente si la necesita para el expediente.",
        )
        return None


def _build_nombre_completo(*parts: str | None) -> str | None:
    values = [part for part in parts if part]
    return " ".join(values) if values else None


def _normalize_doc_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^A-Z ]", " ", _strip_accents(value).upper().replace(".", " "))
    normalized = " ".join(normalized.split())
    normalized = re.split(r"\bDOCUMENTO\b", normalized, maxsplit=1)[0].strip()
    token = normalized.split()[0] if normalized else ""
    if token in {"C", "CC", "CE", "TI", "PA", "RC"}:
        return token
    compact = normalized.replace(" ", "")
    aliases = {
        "CEDULA": "CC",
        "CEDULADECIUDADANIA": "CC",
        "CEDULADEEXTRANJERIA": "CE",
        "TARJETAIDENTIDAD": "TI",
        "TARJETADEIDENTIDAD": "TI",
        "PASAPORTE": "PA",
        "REGISTROCIVIL": "RC",
    }
    return aliases.get(compact, compact)


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


def _ensure_page_limit(page_count: int) -> None:
    if page_count > MAX_PDF_PAGES:
        raise CetilExtractionError(
            f"El PDF CETIL tiene {page_count} páginas y el límite es {MAX_PDF_PAGES}. "
            "Separe el certificado o cargue solo las páginas del trabajador."
        )


def _describe_read_failure(failures: list[tuple[str, Exception]]) -> str:
    """Traduce fallos de lectores PDF a una causa accionable."""
    if not failures:
        return (
            "No se pudo leer el PDF CETIL: no hay un lector PDF disponible. "
            "Instale pdfplumber o PyMuPDF."
        )

    type_names = {type(exc).__name__.lower() for _reader, exc in failures}
    messages = " ".join(str(exc) for _reader, exc in failures).lower()

    if any("password" in name or "encrypt" in name for name in type_names) or "password" in messages:
        return (
            "El PDF CETIL está protegido con contraseña. "
            "Descárguelo sin cifrado y vuelva a intentarlo."
        )
    if (
        any("syntax" in name or "xref" in name or "pdfread" in name for name in type_names)
        or "not a pdf" in messages
        or "cannot recognize" in messages
    ):
        return (
            "El archivo no es un PDF válido o está dañado. "
            "Vuelva a descargar el CETIL original y cárguelo de nuevo."
        )

    detail = "; ".join(f"{reader}: {type(exc).__name__}: {exc}" for reader, exc in failures)
    return f"No se pudo leer el PDF CETIL. Detalle técnico: {detail}"


def _empty_text_issue(
    ocr_error_code: str | None,
    ocr_error_detail: str | None,
) -> dict[str, object]:
    """Construye la incidencia de bloqueo cuando no hay texto utilizable."""
    common: dict[str, object] = {
        "severity": IssueSeverity.BLOCK,
        "field": "documento",
        "locator": "capa de texto",
    }
    if ocr_error_code == OCR_UNAVAILABLE:
        return {
            **common,
            "code": ExtractionIssueCode.OCR_UNAVAILABLE,
            "message": (
                "El PDF no contiene capa de texto y el OCR opcional no está disponible. "
                "No se calculó nada con este archivo."
            ),
            "cause": ocr_error_detail or "Faltan dependencias o el binario de Tesseract.",
            "action": (
                "Instale el extra OCR con `pip install -e .[ocr]` y el binario de Tesseract, "
                "o solicite el CETIL original en PDF con texto."
            ),
        }
    if ocr_error_code == OCR_FAILED:
        return {
            **common,
            "code": ExtractionIssueCode.OCR_FAILED,
            "message": (
                "El PDF no contiene capa de texto y el OCR falló durante el procesamiento. "
                "No se calculó nada con este archivo."
            ),
            "cause": ocr_error_detail or "El OCR no pudo procesar las páginas.",
            "action": (
                "Verifique el PDF o intente con una copia con mejor resolución. "
                "También puede solicitar el CETIL original con texto."
            ),
        }
    if ocr_error_code == OCR_NO_TEXT:
        return {
            **common,
            "code": ExtractionIssueCode.OCR_NO_TEXT,
            "message": (
                "El OCR se ejecutó, pero no reconoció texto legible en el CETIL. "
                "No se calculó nada con este archivo."
            ),
            "cause": ocr_error_detail or "Las páginas no contienen texto reconocible.",
            "action": (
                "Cargue una versión escaneada con mayor calidad o el CETIL original con texto."
            ),
        }
    return {
        **common,
        "code": ExtractionIssueCode.PDF_NO_TEXT_LAYER,
        "message": (
            "El PDF no contiene capa de texto: parece un documento escaneado "
            "y no puede extraerse sin OCR."
        ),
        "cause": "Todas las páginas devolvieron texto vacío al leerlas.",
        "action": (
            "Solicite el CETIL original en PDF con texto o digitalícelo con OCR "
            "antes de cargarlo. No se calculó nada con este archivo."
        ),
    }
