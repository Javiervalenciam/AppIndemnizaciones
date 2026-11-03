"""Registro de varios certificados CETIL para una misma persona.

Una liquidación puede requerir más de un CETIL (varias vinculaciones, un
certificado complementario o una versión actualizada). Este módulo conserva
todos los documentos cargados, detecta duplicados, conflictos de identidad y
periodos contradictorios, y produce una fila por periodo con su procedencia.

Reglas:
- Nunca se descarta un documento en silencio: agregar, duplicar o rechazar
  siempre deja una incidencia trazable.
- Nunca se elige un valor salarial contradictorio sin revisión humana.
- El orden de carga no altera el resultado: la consolidación es determinista.
- Las etiquetas y mensajes no contienen datos personales del trabajador.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app_indemnizaciones.services.cetil_models import (
    CetilEntidadEmpleadora,
    CetilExtractionResult,
    CetilMetadata,
    CetilTrabajador,
    ExtractionIssue,
    ExtractionIssueCode,
    ExtractionIssueLog,
    IssueSeverity,
    PeriodoLiquidableAnual,
    cetil_result_from_dict,
    cetil_result_to_dict,
)
from app_indemnizaciones.services.period_normalizer import (
    normalize_cetil_to_annual_periods,
    periodo_liquidable_to_ui_row,
)

_DOCUMENT_KEY_SEPARATOR = "|"


@dataclass(frozen=True)
class CetilDocumento:
    """Certificado CETIL cargado en la sesión con su extracción ya hecha."""

    documento_id: str
    content_hash: str
    resultado: CetilExtractionResult
    filename: str | None = None

    # Propiedades de lectura: la UI y los exportadores no deben recalcular.

    @property
    def numero_cetil(self) -> str | None:
        metadata = self.resultado.metadata
        return metadata.numero_cetil if metadata else None

    @property
    def fecha_expedicion(self) -> date | None:
        metadata = self.resultado.metadata
        return metadata.fecha_expedicion_cetil if metadata else None

    @property
    def documento_trabajador(self) -> str | None:
        trabajador = self.resultado.trabajador
        return trabajador.documento if trabajador else None

    @property
    def etiqueta(self) -> str:
        """Etiqueta corta para trazabilidad y selección en la UI.

        No incluye nombre ni documento del trabajador. Si el CETIL no trae
        número, usa el nombre del archivo elegido por el usuario.
        """
        parts: list[str] = []
        if self.numero_cetil:
            parts.append(f"CETIL {self.numero_cetil}")
        elif self.filename:
            parts.append(self.filename)
        else:
            parts.append("CETIL sin identificar")
        if self.fecha_expedicion:
            parts.append(self.fecha_expedicion.isoformat())
        return " · ".join(parts)

    @property
    def periodos_anuales(self) -> int:
        return len(_annual_rows(self.resultado))


def create_documento(
    resultado: CetilExtractionResult,
    *,
    filename: str | None = None,
    content_hash: str | None = None,
) -> CetilDocumento:
    """Construye el documento con un identificador estable y sin PII."""
    digest = content_hash or _default_content_hash(resultado)
    return CetilDocumento(
        documento_id=f"cetil-{digest[:12]}",
        content_hash=digest,
        filename=filename,
        resultado=resultado,
    )


def add_documento(
    documentos: list[CetilDocumento],
    nuevo: CetilDocumento,
) -> tuple[list[CetilDocumento], list[ExtractionIssue]]:
    """Agrega un documento validando duplicidad e identidad.

    Devuelve la lista resultante y las incidencias nuevas. Un documento
    duplicado o de otra persona no se agrega: se informa con severidad y
    acción para que el usuario decida.
    """
    log = ExtractionIssueLog()

    for existente in documentos:
        if _is_same_document(existente, nuevo):
            log.add(
                code=ExtractionIssueCode.MULTI_DOCUMENT_DUPLICATE,
                severity=IssueSeverity.WARNING,
                message=(
                    f"El certificado {nuevo.etiqueta} ya estaba cargado; "
                    "no se agregó de nuevo."
                ),
                field="cetil.documentos",
                locator=nuevo.etiqueta,
                cause="Coincide el contenido o el número y la fecha de expedición.",
                action="Continúe con los documentos ya cargados o limpie la sesión CETIL.",
            )
            return list(documentos), log.issues

    if documentos:
        referencias = {
            _normalize_documento(documento.documento_trabajador) for documento in documentos
        }
        referencias.discard("")
        candidato = _normalize_documento(nuevo.documento_trabajador)
        if referencias and candidato and candidato not in referencias:
            log.add(
                code=ExtractionIssueCode.MULTI_IDENTITY_CONFLICT,
                severity=IssueSeverity.ERROR,
                message=(
                    f"El certificado {nuevo.etiqueta} pertenece a un documento de "
                    "identidad distinto al de los certificados ya cargados."
                ),
                field="trabajador.documento",
                locator=nuevo.etiqueta,
                cause="Los CETIL de la sesión deben corresponder al mismo trabajador.",
                action=(
                    "Verifique el número de documento en el PDF. Si es otra persona, "
                    "limpie la sesión CETIL antes de cargarlo."
                ),
            )
            return list(documentos), log.issues
        if len(referencias) > 1:
            log.add(
                code=ExtractionIssueCode.MULTI_IDENTITY_UNVERIFIED,
                severity=IssueSeverity.REVIEW_REQUIRED,
                message=(
                    "Los certificados ya cargados tienen números de documento distintos; "
                    "confirme cuáles corresponden al mismo trabajador."
                ),
                field="trabajador.documento",
                locator=nuevo.etiqueta,
                cause="Una carga previa quedó sin identidad verificada.",
                action=(
                    "Compare los PDF y quite los certificados de otras personas antes de calcular."
                ),
            )
        elif not referencias or not candidato:
            log.add(
                code=ExtractionIssueCode.MULTI_IDENTITY_UNVERIFIED,
                severity=IssueSeverity.REVIEW_REQUIRED,
                message=(
                    "No fue posible confirmar que los certificados correspondan al "
                    "mismo trabajador porque falta el número de documento en alguno."
                ),
                field="trabajador.documento",
                locator=nuevo.etiqueta,
                cause="El CETIL no trae documento legible o no fue detectado.",
                action="Compare nombres y documentos en los PDF antes de calcular.",
            )

    resultado = [*documentos, nuevo]
    log.add(
        code=ExtractionIssueCode.MULTI_DOCUMENT_ADDED,
        severity=IssueSeverity.INFO,
        message=(
            f"Se agregó el certificado {nuevo.etiqueta} "
            f"({nuevo.periodos_anuales} fila(s) anual(es))."
        ),
        field="cetil.documentos",
        locator=nuevo.etiqueta,
    )
    return resultado, log.issues


def remove_documento(
    documentos: list[CetilDocumento],
    documento_id: str,
) -> list[CetilDocumento]:
    return [doc for doc in documentos if doc.documento_id != documento_id]


def merge_resultados(documentos: list[CetilDocumento]) -> CetilExtractionResult:
    """Une los documentos en un solo resultado para resumen, cálculo y export.

    Las filas anuales se consolidan antes de exponerse: un periodo idéntico
    repetido en varios CETIL se conserva una sola vez (del certificado más
    reciente); un periodo contradictorio o solapado se conserva completo con
    una incidencia de revisión. La procedencia de cada fila queda en
    `documento_cetil`.
    """
    if not documentos:
        return CetilExtractionResult()

    # La consolidación no depende del orden de carga: se procesa siempre en el
    # mismo orden determinista (expedición, hash e identificador).
    documentos = sorted(
        documentos,
        key=lambda documento: (
            documento.fecha_expedicion or date.min,
            documento.content_hash,
            documento.documento_id,
        ),
    )

    candidatas: list[tuple[PeriodoLiquidableAnual, int]] = []
    periodos = []
    factores = []
    log = ExtractionIssueLog()
    scores: list[float] = []

    for orden, documento in enumerate(documentos):
        resultado = documento.resultado
        periodos.extend(resultado.periodos_certificados)
        factores.extend(resultado.factores_salariales)
        for fila in _annual_rows(resultado):
            candidatas.append((replace(fila, documento_cetil=documento.etiqueta), orden))
        log.extend(resultado.issues)
        if resultado.confidence_score is not None:
            scores.append(resultado.confidence_score)

    filas, issues = _consolidar_filas(candidatas, documentos)
    log.extend(issues)

    return CetilExtractionResult(
        metadata=_first_metadata(documentos),
        trabajador=_first_trabajador(documentos),
        entidad_empleadora=_first_entidad(documentos),
        entidad_certificadora=documentos[0].resultado.entidad_certificadora,
        periodos_certificados=periodos,
        factores_salariales=factores,
        filas_liquidables_anuales=filas,
        advertencias=log.warnings,
        issues=log.issues,
        texto_paginas=dict(documentos[0].resultado.texto_paginas),
        # La confianza agregada es la del documento menos confiable.
        confidence_score=min(scores) if scores else None,
    )


def merge_document_rows(
    documentos: list[CetilDocumento],
) -> tuple[list[dict[str, str]], list[ExtractionIssue]]:
    """Filas de la tabla de revisión para todos los certificados cargados.

    Delega en `merge_resultados` para que la tabla, el resumen, el cálculo y
    la exportación compartan exactamente el mismo conjunto de periodos.
    """
    merged = merge_resultados(documentos)
    rows = [periodo_liquidable_to_ui_row(fila) for fila in merged.filas_liquidables_anuales]
    return rows, list(merged.issues)


def documentos_to_state(documentos: list[CetilDocumento]) -> list[dict[str, Any]]:
    return [
        {
            "documento_id": doc.documento_id,
            "content_hash": doc.content_hash,
            "filename": doc.filename,
            "resultado": cetil_result_to_dict(doc.resultado),
        }
        for doc in documentos
    ]


def documentos_from_state(data: list[dict[str, Any]] | None) -> list[CetilDocumento]:
    documentos: list[CetilDocumento] = []
    for raw in data or []:
        documentos.append(
            CetilDocumento(
                documento_id=raw["documento_id"],
                content_hash=raw.get("content_hash", ""),
                filename=raw.get("filename"),
                resultado=cetil_result_from_dict(raw.get("resultado")),
            )
        )
    return documentos


def content_hash_of_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _default_content_hash(resultado: CetilExtractionResult) -> str:
    """Hash estable de los campos que identifican el certificado.

    No incluye el texto completo del PDF para no cargar páginas enteras en el
    almacenamiento del navegador y para que el hash no exponga contenido.
    """
    metadata = resultado.metadata
    partes: list[str] = [
        metadata.numero_cetil if metadata and metadata.numero_cetil else "",
        metadata.fecha_expedicion_cetil.isoformat()
        if metadata and metadata.fecha_expedicion_cetil
        else "",
        _normalize_documento(resultado.trabajador.documento if resultado.trabajador else None),
    ]
    for periodo in resultado.periodos_certificados:
        partes.append(
            _DOCUMENT_KEY_SEPARATOR.join(
                [
                    periodo.fecha_desde.isoformat() if periodo.fecha_desde else "",
                    periodo.fecha_hasta.isoformat() if periodo.fecha_hasta else "",
                    periodo.entidad_responsable or "",
                ]
            )
        )
    for factor in resultado.factores_salariales:
        partes.append(f"{factor.anio}:{factor.ibl_sugerido}")
    return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()


def _annual_rows(resultado: CetilExtractionResult) -> list[PeriodoLiquidableAnual]:
    if resultado.filas_liquidables_anuales:
        return resultado.filas_liquidables_anuales
    filas, _warnings = normalize_cetil_to_annual_periods(resultado)
    return filas


def _is_same_document(existente: CetilDocumento, nuevo: CetilDocumento) -> bool:
    if existente.content_hash and existente.content_hash == nuevo.content_hash:
        return True
    return bool(
        existente.numero_cetil
        and nuevo.numero_cetil
        and existente.numero_cetil == nuevo.numero_cetil
        and existente.fecha_expedicion == nuevo.fecha_expedicion
    )


def _normalize_documento(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _consolidar_filas(
    candidatas: list[tuple[PeriodoLiquidableAnual, int]],
    documentos: list[CetilDocumento],
) -> tuple[list[PeriodoLiquidableAnual], list[ExtractionIssue]]:
    """Consolida las filas anuales de todos los certificados.

    - Mismo periodo y mismos valores: se conserva el certificado más reciente.
    - Mismo periodo con valores distintos: se conservan todas las filas.
    - Periodos parcialmente solapados: se conservan todas las filas.
    """
    log = ExtractionIssueLog()
    grupos: dict[tuple[date, date], list[tuple[PeriodoLiquidableAnual, int]]] = {}
    for fila, orden in candidatas:
        grupos.setdefault((fila.fecha_inicio, fila.fecha_fin), []).append((fila, orden))

    conservadas: list[PeriodoLiquidableAnual] = []
    for (inicio, fin), entradas in sorted(grupos.items()):
        if len(entradas) == 1:
            conservadas.append(entradas[0][0])
            continue
        if _filas_equivalentes([fila for fila, _orden in entradas]):
            ganadora, _orden = max(
                entradas, key=lambda entrada: _recencia(entrada[1], documentos)
            )
            descartadas = [fila for fila, _orden in entradas if fila is not ganadora]
            log.add(
                code=ExtractionIssueCode.MULTI_PERIOD_DUPLICATE,
                severity=IssueSeverity.INFO,
                message=(
                    f"El periodo {inicio.isoformat()}..{fin.isoformat()} aparece en "
                    f"{len(entradas)} certificados con los mismos valores; se conserva "
                    f"{ganadora.documento_cetil or 'el certificado más reciente'}."
                ),
                field="filas_liquidables_anuales",
                locator=" · ".join(
                    sorted({fila.documento_cetil or "" for fila in descartadas})
                ),
                cause="Carga repetida o certificado actualizado sin cambios salariales.",
                action=(
                    "Confirme que el certificado conservado es el vigente; "
                    "las demás filas se omitieron para no duplicar días."
                ),
            )
            conservadas.append(ganadora)
            continue

        log.add(
            code=ExtractionIssueCode.MULTI_PERIOD_CONFLICT,
            severity=IssueSeverity.REVIEW_REQUIRED,
            message=(
                f"El periodo {inicio.isoformat()}..{fin.isoformat()} aparece en "
                f"{len(entradas)} certificados con valores distintos: "
                + "; ".join(
                    f"{fila.documento_cetil or 'certificado sin identificar'} "
                    f"(IBL {fila.ibl_reportado if fila.ibl_reportado is not None else 'sin IBL'})"
                    for fila, _orden in sorted(
                        entradas, key=lambda entrada: _recencia(entrada[1], documentos)
                    )
                )
                + "."
            ),
            field="filas_liquidables_anuales",
            locator=" · ".join(
                sorted({fila.documento_cetil or "" for fila, _orden in entradas})
            ),
            cause="Dos CETIL cubren el mismo periodo con IBL, cargo o entidad diferentes.",
            action=(
                "Determine cuál certificado rige el periodo y deje una sola fila "
                "con el IBL correcto antes de calcular."
            ),
        )
        conservadas.extend(fila for fila, _orden in entradas)

    conservadas.sort(
        key=lambda fila: (fila.fecha_inicio, fila.fecha_fin, fila.documento_cetil or "")
    )
    log.extend(_overlap_issues(conservadas))
    return conservadas, log.issues


def _filas_equivalentes(filas: list[PeriodoLiquidableAnual]) -> bool:
    return len({_clave_salarial(fila) for fila in filas}) == 1


def _clave_salarial(fila: PeriodoLiquidableAnual) -> tuple[str, str, str]:
    return (
        _decimal_key(fila.ibl_reportado),
        (fila.cargo or "").strip().lower(),
        (fila.entidad or "").strip().lower(),
    )


def _decimal_key(value: Decimal | None) -> str:
    if value is None:
        return ""
    try:
        return str(Decimal(value).normalize())
    except InvalidOperation:  # pragma: no cover - Decimal ya validado aguas arriba
        return str(value)


def _recencia(orden: int, documentos: list[CetilDocumento]) -> tuple[date, str]:
    """Clave de precedencia determinista, independiente del orden de carga.

    Primero la fecha de expedición y, si empatan, el hash del contenido.
    """
    documento = documentos[orden]
    return (documento.fecha_expedicion or date.min, documento.content_hash)


def _overlap_issues(filas: list[PeriodoLiquidableAnual]) -> list[ExtractionIssue]:
    issues: list[ExtractionIssue] = []
    for indice, actual in enumerate(filas):
        for siguiente in filas[indice + 1 :]:
            if siguiente.fecha_inicio > actual.fecha_fin:
                break
            if actual.documento_cetil == siguiente.documento_cetil:
                continue
            issues.append(
                ExtractionIssue(
                    code=ExtractionIssueCode.MULTI_PERIOD_OVERLAP,
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    message=(
                        f"Los periodos {actual.fecha_inicio.isoformat()}"
                        f"..{actual.fecha_fin.isoformat()} y "
                        f"{siguiente.fecha_inicio.isoformat()}"
                        f"..{siguiente.fecha_fin.isoformat()} se "
                        "solapan entre certificados; los días podrían contarse dos veces."
                    ),
                    field="filas_liquidables_anuales",
                    locator=(
                        f"{actual.documento_cetil or 'sin identificar'} · "
                        f"{siguiente.documento_cetil or 'sin identificar'}"
                    ),
                    cause="Dos CETIL cubren días en común.",
                    action=(
                        "Ajuste las fechas para que cada día quede en un solo periodo "
                        "y vuelva a revisar el total de días."
                    ),
                )
            )
    return issues


def _first_metadata(documentos: list[CetilDocumento]) -> CetilMetadata | None:
    for documento in documentos:
        if documento.resultado.metadata is not None:
            return documento.resultado.metadata
    return None


def _first_trabajador(documentos: list[CetilDocumento]) -> CetilTrabajador | None:
    for documento in documentos:
        if documento.resultado.trabajador is not None:
            return documento.resultado.trabajador
    return None


def _first_entidad(documentos: list[CetilDocumento]) -> CetilEntidadEmpleadora | None:
    for documento in documentos:
        if documento.resultado.entidad_empleadora is not None:
            return documento.resultado.entidad_empleadora
    return None
