from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


class IssueSeverity(StrEnum):
    """Severidad de una incidencia de extracción CETIL.

    El orden importa: la UI y el flujo de importación usan `rank` para decidir
    si el documento puede continuar hacia la liquidación.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ERROR = "ERROR"
    BLOCK = "BLOCK"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]

    @property
    def label(self) -> str:
        return _SEVERITY_LABEL[self]


_SEVERITY_RANK: dict[IssueSeverity, int] = {
    IssueSeverity.INFO: 0,
    IssueSeverity.WARNING: 1,
    IssueSeverity.REVIEW_REQUIRED: 2,
    IssueSeverity.ERROR: 3,
    IssueSeverity.BLOCK: 4,
}

_SEVERITY_LABEL: dict[IssueSeverity, str] = {
    IssueSeverity.INFO: "Informativa",
    IssueSeverity.WARNING: "Advertencia",
    IssueSeverity.REVIEW_REQUIRED: "Requiere revisión",
    IssueSeverity.ERROR: "Error",
    IssueSeverity.BLOCK: "Bloqueo",
}


class ExtractionIssueCode(StrEnum):
    """Códigos estables para soporte y pruebas.

    Un código no debe reutilizarse con otro significado: los usuarios y los
    logs de soporte lo citan textualmente.
    """

    PDF_NO_TEXT_LAYER = "CETIL_PDF_NO_TEXT_LAYER"
    PDF_PAGE_WITHOUT_TEXT = "CETIL_PDF_PAGE_WITHOUT_TEXT"
    PDF_TOO_MANY_PAGES = "CETIL_PDF_TOO_MANY_PAGES"
    PDF_ENCRYPTED = "CETIL_PDF_ENCRYPTED"
    PDF_CORRUPT = "CETIL_PDF_CORRUPT"
    PDF_UNREADABLE = "CETIL_PDF_UNREADABLE"
    OCR_APPLIED_REVIEW_REQUIRED = "CETIL_OCR_APPLIED_REVIEW_REQUIRED"
    OCR_UNAVAILABLE = "CETIL_OCR_UNAVAILABLE"
    OCR_FAILED = "CETIL_OCR_FAILED"
    OCR_NO_TEXT = "CETIL_OCR_NO_TEXT"

    METADATA_MISSING = "CETIL_METADATA_MISSING"
    DOCUMENT_DATE_UNPARSEABLE = "CETIL_DOCUMENT_DATE_UNPARSEABLE"

    WORKER_DATA_MISSING = "CETIL_WORKER_DATA_MISSING"
    WORKER_GENDER_MISSING = "CETIL_WORKER_GENDER_MISSING"

    ENTITY_SECTION_MISSING = "CETIL_ENTITY_SECTION_MISSING"
    ENTITY_NAME_MISSING = "CETIL_ENTITY_NAME_MISSING"
    ENTITY_NIT_MISSING = "CETIL_ENTITY_NIT_MISSING"

    PERIODS_MISSING = "CETIL_PERIODS_MISSING"
    PERIODS_TABLE_ROW_INVALID = "CETIL_PERIODS_TABLE_ROW_INVALID"
    PERIODS_DECLARED_DAYS_INCONSISTENT = "CETIL_PERIODS_DECLARED_DAYS_INCONSISTENT"

    SALARY_BLOCKS_MISSING = "CETIL_SALARY_BLOCKS_MISSING"
    SALARY_BLOCK_SPLIT_PAGES = "CETIL_SALARY_BLOCK_SPLIT_PAGES"
    SALARY_YEAR_WITHOUT_VALUES = "CETIL_SALARY_YEAR_WITHOUT_VALUES"
    SALARY_MONTHS_INCOMPLETE = "CETIL_SALARY_MONTHS_INCOMPLETE"
    IBL_NOT_FOUND = "CETIL_IBL_NOT_FOUND"
    IBL_AMBIGUOUS = "CETIL_IBL_AMBIGUOUS"
    IBL_ATYPICAL = "CETIL_IBL_ATYPICAL"
    IBL_MANUAL_REQUIRED = "CETIL_IBL_MANUAL_REQUIRED"

    ANNUALIZATION_DATE_LOST = "CETIL_ANNUALIZATION_DATE_LOST"
    YEAR_GAP = "CETIL_YEAR_GAP"

    MULTI_DOCUMENT_ADDED = "CETIL_MULTI_DOCUMENT_ADDED"
    MULTI_DOCUMENT_DUPLICATE = "CETIL_MULTI_DOCUMENT_DUPLICATE"
    MULTI_IDENTITY_CONFLICT = "CETIL_MULTI_IDENTITY_CONFLICT"
    MULTI_IDENTITY_UNVERIFIED = "CETIL_MULTI_IDENTITY_UNVERIFIED"
    MULTI_PERIOD_DUPLICATE = "CETIL_MULTI_PERIOD_DUPLICATE"
    MULTI_PERIOD_CONFLICT = "CETIL_MULTI_PERIOD_CONFLICT"
    MULTI_PERIOD_OVERLAP = "CETIL_MULTI_PERIOD_OVERLAP"


@dataclass(frozen=True)
class ExtractionIssue:
    """Incidencia trazable del proceso de extracción.

    Regla de privacidad: `message`, `locator` y `action` NUNCA deben contener
    datos personales del trabajador (nombre, documento, dirección). Solo
    describen el campo, la página, la causa técnica y la acción esperada.
    """

    code: ExtractionIssueCode
    severity: IssueSeverity
    message: str
    field: str | None = None
    page: int | None = None
    locator: str | None = None
    cause: str | None = None
    action: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.severity is IssueSeverity.BLOCK

    @property
    def needs_attention(self) -> bool:
        return self.severity.rank >= IssueSeverity.REVIEW_REQUIRED.rank


@dataclass
class ExtractionIssueLog:
    """Acumula incidencias y conserva la lista plana de advertencias legada.

    `warnings` mantiene compatibilidad con el contrato anterior
    (`CetilExtractionResult.advertencias`), mientras `issues` agrega
    severidad, campo, página y causa.
    """

    issues: list[ExtractionIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add(
        self,
        *,
        code: ExtractionIssueCode,
        severity: IssueSeverity,
        message: str,
        field: str | None = None,
        page: int | None = None,
        locator: str | None = None,
        cause: str | None = None,
        action: str | None = None,
    ) -> None:
        if any(
            issue.code is code
            and issue.message == message
            and issue.field == field
            and issue.page == page
            for issue in self.issues
        ):
            return
        self.issues.append(
            ExtractionIssue(
                code=code,
                severity=severity,
                message=message,
                field=field,
                page=page,
                locator=locator,
                cause=cause,
                action=action,
            )
        )
        if message not in self.warnings:
            self.warnings.append(message)

    def extend(self, issues: list[ExtractionIssue]) -> None:
        for issue in issues:
            self.add(
                code=issue.code,
                severity=issue.severity,
                message=issue.message,
                field=issue.field,
                page=issue.page,
                locator=issue.locator,
                cause=issue.cause,
                action=issue.action,
            )

    @property
    def has_blocking(self) -> bool:
        return any(issue.is_blocking for issue in self.issues)

    @property
    def highest_severity(self) -> IssueSeverity | None:
        return highest_issue_severity(self.issues)


def highest_issue_severity(issues: list[ExtractionIssue]) -> IssueSeverity | None:
    if not issues:
        return None
    return max((issue.severity for issue in issues), key=lambda severity: severity.rank)


def count_issues_by_severity(issues: list[ExtractionIssue]) -> dict[str, int]:
    counts = {severity.value: 0 for severity in IssueSeverity}
    for issue in issues:
        counts[issue.severity.value] += 1
    return counts


@dataclass(frozen=True)
class CetilMetadata:
    numero_cetil: str | None = None
    ciudad_expedicion: str | None = None
    fecha_expedicion_cetil: date | None = None


@dataclass(frozen=True)
class CetilTrabajador:
    tipo_documento: str | None = None
    documento: str | None = None
    primer_apellido: str | None = None
    segundo_apellido: str | None = None
    primer_nombre: str | None = None
    segundo_nombre: str | None = None
    nombre_completo: str | None = None
    fecha_nacimiento: date | None = None
    genero: str | None = None
    genero_origen: str | None = None  # None/'cetil' = viene del PDF; 'base_nombres' = inferido


@dataclass(frozen=True)
class CetilEntidadEmpleadora:
    nombre_entidad_empleadora: str | None = None
    nit_entidad_empleadora: str | None = None
    fecha_vigencia_sistema_general_pensiones: date | None = None


@dataclass(frozen=True)
class CetilPeriodoCertificado:
    fecha_desde: date | None
    fecha_hasta: date | None
    tipo_vinculacion: str | None = None
    tipo_empleado: str | None = None
    cargo: str | None = None
    aportes_pension: str | None = None
    aportes_salud: str | None = None
    aportes_riesgos: str | None = None
    fondo_aporte: str | None = None
    entidad_responsable: str | None = None
    total_no_dias: int | None = None
    # `total_no_dias` es un alias legado del campo del CETIL "Total No. Días
    # Interrupción". No significa días laborados: los días laborados se derivan
    # de fecha_desde/fecha_hasta.
    dias_interrupcion: int | None = None
    interrupcion: str | None = None
    cargo_alto_riesgo: str | None = None
    tiempo_completo: str | None = None
    horas_semanales_laboradas: str | None = None
    fuente_pagina: int | None = None
    raw_text: str = ""


@dataclass(frozen=True)
class CetilFactorSalarial:
    anio: int
    concepto: str
    periodicidad: str | None = None
    valores_mensuales: dict[str, Decimal | None] = field(default_factory=dict)
    valores_encontrados: list[Decimal] = field(default_factory=list)
    asignacion_basica_mensual: Decimal | None = None
    total_devengado: Decimal | None = None
    ibl_sugerido: Decimal | None = None
    total_devengado_mensual: dict[str, Decimal | None] = field(default_factory=dict)
    # El CETIL marca con "S"/"N" si el factor hace parte del IBC en cada mes.
    # `None` significa que el certificado no trae la marca para ese mes.
    c_ibc_mensual: dict[str, bool | None] = field(default_factory=dict)
    ibl_metodo: str | None = None
    ibl_evidencia: str | None = None
    ibl_requiere_revision: bool = False
    fuente_pagina: int | None = None
    raw_text: str = ""


@dataclass(frozen=True)
class PeriodoLiquidableAnual:
    anio: int
    fecha_inicio: date
    fecha_fin: date
    ibl_reportado: Decimal | None = None
    cargo: str | None = None
    entidad: str | None = None
    fuente: str = "cetil"
    observaciones: str = "Periodo anualizado desde CETIL. Revisar IBL antes de calcular."
    periodo_origen: str | None = None
    # Etiqueta legible del CETIL de origen cuando la sesión tiene varios
    # documentos; permite rastrear cada fila hasta su certificado.
    documento_cetil: str | None = None
    fuente_pagina: int | None = None
    ibl_metodo: str | None = None
    ibl_evidencia: str | None = None
    ibl_requiere_revision: bool = False


@dataclass(frozen=True)
class CetilExtractionResult:
    metadata: CetilMetadata | None = None
    trabajador: CetilTrabajador | None = None
    entidad_empleadora: CetilEntidadEmpleadora | None = None
    entidad_certificadora: str | None = None
    periodos_certificados: list[CetilPeriodoCertificado] = field(default_factory=list)
    factores_salariales: list[CetilFactorSalarial] = field(default_factory=list)
    filas_liquidables_anuales: list[PeriodoLiquidableAnual] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    issues: list[ExtractionIssue] = field(default_factory=list)
    texto_paginas: dict[int, str] = field(default_factory=dict)
    confidence_score: float | None = None


def cetil_result_to_dict(result: CetilExtractionResult) -> dict[str, Any]:
    return {
        "metadata": _metadata_to_dict(result.metadata),
        "trabajador": _trabajador_to_dict(result.trabajador),
        "entidad_empleadora": _entidad_empleadora_to_dict(result.entidad_empleadora),
        "entidad_certificadora": result.entidad_certificadora,
        "periodos_certificados": [_periodo_to_dict(row) for row in result.periodos_certificados],
        "factores_salariales": [_factor_to_dict(row) for row in result.factores_salariales],
        "filas_liquidables_anuales": [
            _periodo_liquidable_to_dict(row) for row in result.filas_liquidables_anuales
        ],
        "advertencias": list(result.advertencias),
        "issues": [_issue_to_dict(issue) for issue in result.issues],
        "texto_paginas": {str(page): text for page, text in result.texto_paginas.items()},
        "confidence_score": result.confidence_score,
    }


def cetil_result_from_dict(data: dict[str, Any] | None) -> CetilExtractionResult:
    payload = data or {}
    return CetilExtractionResult(
        metadata=_metadata_from_dict(payload.get("metadata")),
        trabajador=_trabajador_from_dict(payload.get("trabajador")),
        entidad_empleadora=_entidad_empleadora_from_dict(payload.get("entidad_empleadora")),
        entidad_certificadora=payload.get("entidad_certificadora"),
        periodos_certificados=[
            _periodo_from_dict(row) for row in payload.get("periodos_certificados", [])
        ],
        factores_salariales=[_factor_from_dict(row) for row in payload.get("factores_salariales", [])],
        filas_liquidables_anuales=[
            _periodo_liquidable_from_dict(row)
            for row in payload.get("filas_liquidables_anuales", [])
        ],
        advertencias=list(payload.get("advertencias", [])),
        issues=[_issue_from_dict(raw) for raw in payload.get("issues", [])],
        texto_paginas={int(page): text for page, text in payload.get("texto_paginas", {}).items()},
        confidence_score=payload.get("confidence_score"),
    )


def _date_to_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date_from_str(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _decimal_map_to_dict(values: dict[str, Decimal | None]) -> dict[str, str | None]:
    return {key: str(value) if value is not None else None for key, value in values.items()}


def _decimal_map_from_dict(values: dict[str, Any] | None) -> dict[str, Decimal | None]:
    return {key: Decimal(str(value)) if value is not None else None for key, value in (values or {}).items()}


def _decimal_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal_from_str(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _issue_to_dict(issue: ExtractionIssue) -> dict[str, Any]:
    return {
        "code": issue.code.value,
        "severity": issue.severity.value,
        "message": issue.message,
        "field": issue.field,
        "page": issue.page,
        "locator": issue.locator,
        "cause": issue.cause,
        "action": issue.action,
    }


def _issue_from_dict(data: dict[str, Any]) -> ExtractionIssue:
    try:
        code = ExtractionIssueCode(data.get("code", ""))
    except ValueError:
        code = ExtractionIssueCode.PDF_UNREADABLE
    try:
        severity = IssueSeverity(data.get("severity", IssueSeverity.WARNING.value))
    except ValueError:
        severity = IssueSeverity.WARNING
    return ExtractionIssue(
        code=code,
        severity=severity,
        message=data.get("message", ""),
        field=data.get("field"),
        page=data.get("page"),
        locator=data.get("locator"),
        cause=data.get("cause"),
        action=data.get("action"),
    )


def _metadata_to_dict(row: CetilMetadata | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "numero_cetil": row.numero_cetil,
        "ciudad_expedicion": row.ciudad_expedicion,
        "fecha_expedicion_cetil": _date_to_str(row.fecha_expedicion_cetil),
    }


def _metadata_from_dict(data: dict[str, Any] | None) -> CetilMetadata | None:
    if not data:
        return None
    return CetilMetadata(
        numero_cetil=data.get("numero_cetil"),
        ciudad_expedicion=data.get("ciudad_expedicion"),
        fecha_expedicion_cetil=_date_from_str(data.get("fecha_expedicion_cetil")),
    )


def _trabajador_to_dict(row: CetilTrabajador | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "tipo_documento": row.tipo_documento,
        "documento": row.documento,
        "primer_apellido": row.primer_apellido,
        "segundo_apellido": row.segundo_apellido,
        "primer_nombre": row.primer_nombre,
        "segundo_nombre": row.segundo_nombre,
        "nombre_completo": row.nombre_completo,
        "fecha_nacimiento": _date_to_str(row.fecha_nacimiento),
        "genero": row.genero,
        "genero_origen": row.genero_origen,
    }


def _trabajador_from_dict(data: dict[str, Any] | None) -> CetilTrabajador | None:
    if not data:
        return None
    return CetilTrabajador(
        tipo_documento=data.get("tipo_documento"),
        documento=data.get("documento"),
        primer_apellido=data.get("primer_apellido"),
        segundo_apellido=data.get("segundo_apellido"),
        primer_nombre=data.get("primer_nombre"),
        segundo_nombre=data.get("segundo_nombre"),
        nombre_completo=data.get("nombre_completo"),
        fecha_nacimiento=_date_from_str(data.get("fecha_nacimiento")),
        genero=data.get("genero"),
        genero_origen=data.get("genero_origen"),
    )


def _entidad_empleadora_to_dict(row: CetilEntidadEmpleadora | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "nombre_entidad_empleadora": row.nombre_entidad_empleadora,
        "nit_entidad_empleadora": row.nit_entidad_empleadora,
        "fecha_vigencia_sistema_general_pensiones": _date_to_str(
            row.fecha_vigencia_sistema_general_pensiones
        ),
    }


def _entidad_empleadora_from_dict(data: dict[str, Any] | str | None) -> CetilEntidadEmpleadora | None:
    if not data:
        return None
    if isinstance(data, str):
        return CetilEntidadEmpleadora(nombre_entidad_empleadora=data)
    return CetilEntidadEmpleadora(
        nombre_entidad_empleadora=data.get("nombre_entidad_empleadora"),
        nit_entidad_empleadora=data.get("nit_entidad_empleadora"),
        fecha_vigencia_sistema_general_pensiones=_date_from_str(
            data.get("fecha_vigencia_sistema_general_pensiones")
        ),
    )


def _periodo_to_dict(row: CetilPeriodoCertificado) -> dict[str, Any]:
    return {
        "fecha_desde": _date_to_str(row.fecha_desde),
        "fecha_hasta": _date_to_str(row.fecha_hasta),
        "tipo_vinculacion": row.tipo_vinculacion,
        "tipo_empleado": row.tipo_empleado,
        "cargo": row.cargo,
        "aportes_pension": row.aportes_pension,
        "aportes_salud": row.aportes_salud,
        "aportes_riesgos": row.aportes_riesgos,
        "fondo_aporte": row.fondo_aporte,
        "entidad_responsable": row.entidad_responsable,
        "total_no_dias": row.total_no_dias,
        "dias_interrupcion": row.dias_interrupcion,
        "interrupcion": row.interrupcion,
        "cargo_alto_riesgo": row.cargo_alto_riesgo,
        "tiempo_completo": row.tiempo_completo,
        "horas_semanales_laboradas": row.horas_semanales_laboradas,
        "fuente_pagina": row.fuente_pagina,
        "raw_text": row.raw_text,
    }


def _periodo_from_dict(data: dict[str, Any]) -> CetilPeriodoCertificado:
    return CetilPeriodoCertificado(
        fecha_desde=_date_from_str(data.get("fecha_desde")),
        fecha_hasta=_date_from_str(data.get("fecha_hasta")),
        tipo_vinculacion=data.get("tipo_vinculacion"),
        tipo_empleado=data.get("tipo_empleado"),
        cargo=data.get("cargo"),
        aportes_pension=data.get("aportes_pension"),
        aportes_salud=data.get("aportes_salud"),
        aportes_riesgos=data.get("aportes_riesgos"),
        fondo_aporte=data.get("fondo_aporte"),
        entidad_responsable=data.get("entidad_responsable"),
        total_no_dias=data.get("total_no_dias"),
        dias_interrupcion=data.get("dias_interrupcion"),
        interrupcion=data.get("interrupcion"),
        cargo_alto_riesgo=data.get("cargo_alto_riesgo"),
        tiempo_completo=data.get("tiempo_completo"),
        horas_semanales_laboradas=data.get("horas_semanales_laboradas"),
        fuente_pagina=data.get("fuente_pagina"),
        raw_text=data.get("raw_text", ""),
    )


def _factor_to_dict(row: CetilFactorSalarial) -> dict[str, Any]:
    return {
        "anio": row.anio,
        "concepto": row.concepto,
        "periodicidad": row.periodicidad,
        "valores_mensuales": _decimal_map_to_dict(row.valores_mensuales),
        "valores_encontrados": [str(value) for value in row.valores_encontrados],
        "asignacion_basica_mensual": _decimal_to_str(row.asignacion_basica_mensual),
        "total_devengado": _decimal_to_str(row.total_devengado),
        "ibl_sugerido": _decimal_to_str(row.ibl_sugerido),
        "total_devengado_mensual": _decimal_map_to_dict(row.total_devengado_mensual),
        "c_ibc_mensual": dict(row.c_ibc_mensual),
        "ibl_metodo": row.ibl_metodo,
        "ibl_evidencia": row.ibl_evidencia,
        "ibl_requiere_revision": row.ibl_requiere_revision,
        "fuente_pagina": row.fuente_pagina,
        "raw_text": row.raw_text,
    }


def _factor_from_dict(data: dict[str, Any]) -> CetilFactorSalarial:
    return CetilFactorSalarial(
        anio=int(data["anio"]),
        concepto=data["concepto"],
        periodicidad=data.get("periodicidad"),
        valores_mensuales=_decimal_map_from_dict(data.get("valores_mensuales")),
        valores_encontrados=[Decimal(str(value)) for value in data.get("valores_encontrados", [])],
        asignacion_basica_mensual=_decimal_from_str(data.get("asignacion_basica_mensual")),
        total_devengado=_decimal_from_str(data.get("total_devengado")),
        ibl_sugerido=_decimal_from_str(data.get("ibl_sugerido")),
        total_devengado_mensual=_decimal_map_from_dict(data.get("total_devengado_mensual")),
        c_ibc_mensual={
            month: (None if value is None else bool(value))
            for month, value in (data.get("c_ibc_mensual") or {}).items()
        },
        ibl_metodo=data.get("ibl_metodo"),
        ibl_evidencia=data.get("ibl_evidencia"),
        ibl_requiere_revision=bool(data.get("ibl_requiere_revision", False)),
        fuente_pagina=data.get("fuente_pagina"),
        raw_text=data.get("raw_text", ""),
    )


def _periodo_liquidable_to_dict(row: PeriodoLiquidableAnual) -> dict[str, Any]:
    return {
        "anio": row.anio,
        "fecha_inicio": row.fecha_inicio.isoformat(),
        "fecha_fin": row.fecha_fin.isoformat(),
        "ibl_reportado": _decimal_to_str(row.ibl_reportado),
        "cargo": row.cargo,
        "entidad": row.entidad,
        "fuente": row.fuente,
        "observaciones": row.observaciones,
        "periodo_origen": row.periodo_origen,
        "fuente_pagina": row.fuente_pagina,
        "ibl_metodo": row.ibl_metodo,
        "ibl_evidencia": row.ibl_evidencia,
        "ibl_requiere_revision": row.ibl_requiere_revision,
        "documento_cetil": row.documento_cetil,
    }


def _periodo_liquidable_from_dict(data: dict[str, Any]) -> PeriodoLiquidableAnual:
    return PeriodoLiquidableAnual(
        anio=int(data["anio"]),
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]),
        ibl_reportado=_decimal_from_str(data.get("ibl_reportado")),
        cargo=data.get("cargo"),
        entidad=data.get("entidad"),
        fuente=data.get("fuente", "cetil"),
        observaciones=data.get(
            "observaciones",
            "Periodo anualizado desde CETIL. Revisar IBL antes de calcular.",
        ),
        periodo_origen=data.get("periodo_origen"),
        fuente_pagina=data.get("fuente_pagina"),
        ibl_metodo=data.get("ibl_metodo"),
        ibl_evidencia=data.get("ibl_evidencia"),
        ibl_requiere_revision=bool(data.get("ibl_requiere_revision", False)),
        documento_cetil=data.get("documento_cetil"),
    )
