from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
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
    )
