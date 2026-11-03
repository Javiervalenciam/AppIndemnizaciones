from __future__ import annotations

from datetime import date
from decimal import Decimal

from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    CetilFactorSalarial,
    CetilMetadata,
    CetilPeriodoCertificado,
    CetilTrabajador,
    ExtractionIssueCode,
    IssueSeverity,
)
from app_indemnizaciones.services.cetil_registry import (
    add_documento,
    create_documento,
    documentos_from_state,
    documentos_to_state,
    merge_document_rows,
    merge_resultados,
    remove_documento,
)
from app_indemnizaciones.services.period_normalizer import cetil_extraction_to_period_rows


def _resultado(
    *,
    numero: str = "A-1",
    expedicion: date = date(2024, 1, 10),
    documento: str | None = "123456",
    inicio: date = date(1984, 1, 1),
    fin: date = date(1984, 12, 31),
    ibl: Decimal = Decimal("1000"),
    entidad: str = "ALCALDIA DE PRUEBA",
    anio: int = 1984,
) -> CetilExtractionResult:
    return CetilExtractionResult(
        metadata=CetilMetadata(numero_cetil=numero, fecha_expedicion_cetil=expedicion),
        trabajador=CetilTrabajador(documento=documento, nombre_completo="PERSONA DE PRUEBA"),
        periodos_certificados=[
            CetilPeriodoCertificado(
                fecha_desde=inicio,
                fecha_hasta=fin,
                cargo="AUXILIAR",
                entidad_responsable=entidad,
                fuente_pagina=1,
            )
        ],
        factores_salariales=[
            CetilFactorSalarial(
                anio=anio,
                concepto="ASIGNACION BASICA MENSUAL",
                ibl_sugerido=ibl,
            )
        ],
    )


def _documento(resultado: CetilExtractionResult, **kwargs):
    return create_documento(resultado, **kwargs)


def _codigos(issues) -> set[ExtractionIssueCode]:
    return {issue.code for issue in issues}


def test_documentos_complementarios_conservan_todas_las_filas() -> None:
    documentos = [
        _documento(_resultado(numero="A-1", inicio=date(1984, 1, 1), fin=date(1984, 12, 31))),
        _documento(
            _resultado(
                numero="A-2",
                inicio=date(1985, 1, 1),
                fin=date(1985, 12, 31),
                anio=1985,
            )
        ),
    ]

    filas, issues = merge_document_rows(documentos)

    assert [fila["anio"] for fila in filas] == ["1984", "1985"]
    assert len({fila["documento_cetil"] for fila in filas}) == 2
    assert ExtractionIssueCode.MULTI_PERIOD_CONFLICT not in _codigos(issues)
    assert ExtractionIssueCode.MULTI_PERIOD_OVERLAP not in _codigos(issues)


def test_orden_permutado_produce_el_mismo_resultado() -> None:
    a = _documento(_resultado(numero="A-1", inicio=date(1984, 1, 1), fin=date(1984, 12, 31)))
    b = _documento(
        _resultado(numero="A-2", inicio=date(1985, 1, 1), fin=date(1985, 12, 31), anio=1985)
    )

    filas_ab, _ = merge_document_rows([a, b])
    filas_ba, _ = merge_document_rows([b, a])

    assert filas_ab == filas_ba


def test_empate_de_expedicion_se_rompe_por_hash_del_documento() -> None:
    a = _documento(_resultado(numero="A-1", expedicion=date(2024, 5, 1)))
    b = _documento(_resultado(numero="A-2", expedicion=date(2024, 5, 1)))
    esperada = max([a, b], key=lambda doc: (doc.fecha_expedicion, doc.content_hash)).etiqueta

    filas_ab, _ = merge_document_rows([a, b])
    filas_ba, _ = merge_document_rows([b, a])

    assert filas_ab == filas_ba
    assert len(filas_ab) == 1
    assert filas_ab[0]["documento_cetil"] == esperada


def test_documento_duplicado_no_se_agrega_y_advierte() -> None:
    resultado = _resultado()
    documentos, _ = add_documento([], _documento(resultado))

    documentos, issues = add_documento(documentos, _documento(resultado))

    assert len(documentos) == 1
    assert ExtractionIssueCode.MULTI_DOCUMENT_DUPLICATE in _codigos(issues)
    assert issues[0].severity is IssueSeverity.WARNING


def test_documento_de_otra_persona_no_se_agrega_y_es_error() -> None:
    documentos, _ = add_documento([], _documento(_resultado(numero="A-1")))

    documentos, issues = add_documento(
        documentos,
        _documento(_resultado(numero="A-2", documento="999999")),
    )

    assert len(documentos) == 1
    issue = next(issue for issue in issues if issue.code is ExtractionIssueCode.MULTI_IDENTITY_CONFLICT)
    assert issue.severity is IssueSeverity.ERROR
    # La incidencia nunca repite números de documento del trabajador.
    assert "999999" not in issue.message
    assert "123456" not in issue.message


def test_documento_sin_numero_de_identidad_exige_revision() -> None:
    documentos, _ = add_documento([], _documento(_resultado(numero="A-1")))

    documentos, issues = add_documento(
        documentos,
        _documento(_resultado(numero="A-2", documento=None)),
    )

    assert len(documentos) == 2
    assert ExtractionIssueCode.MULTI_IDENTITY_UNVERIFIED in _codigos(issues)


def test_identidad_distinta_se_rechaza_aunque_la_primera_carga_no_tuviera_numero() -> None:
    documentos, _ = add_documento([], _documento(_resultado(numero="A-1", documento=None)))
    documentos, _ = add_documento(
        documentos,
        _documento(_resultado(numero="A-2", documento="111111")),
    )

    documentos, issues = add_documento(
        documentos,
        _documento(_resultado(numero="A-3", documento="222222")),
    )

    assert len(documentos) == 2
    issue = next(
        issue for issue in issues if issue.code is ExtractionIssueCode.MULTI_IDENTITY_CONFLICT
    )
    assert issue.severity is IssueSeverity.ERROR
    assert "111111" not in issue.message
    assert "222222" not in issue.message


def test_periodo_identico_conserva_el_certificado_mas_reciente() -> None:
    antiguo = _documento(_resultado(numero="A-1", expedicion=date(2020, 5, 1)))
    reciente = _documento(_resultado(numero="A-2", expedicion=date(2024, 5, 1)))

    filas, issues = merge_document_rows([reciente, antiguo])

    assert len(filas) == 1
    assert filas[0]["documento_cetil"].startswith("CETIL A-2")
    assert ExtractionIssueCode.MULTI_PERIOD_DUPLICATE in _codigos(issues)


def test_tabla_usa_el_mismo_conjunto_consolidado_y_un_id_estable() -> None:
    antiguo = _documento(_resultado(numero="A-1", expedicion=date(2020, 5, 1)))
    reciente = _documento(_resultado(numero="A-2", expedicion=date(2024, 5, 1)))

    merged = merge_resultados([antiguo, reciente])
    filas = cetil_extraction_to_period_rows(merged)

    assert len(merged.filas_liquidables_anuales) == 1
    assert len(filas) == 1
    assert filas[0]["documento_cetil"].startswith("CETIL A-2")
    assert filas[0]["id"] == cetil_extraction_to_period_rows(merged)[0]["id"]


def test_periodo_contradictorio_mantiene_filas_y_exige_revision() -> None:
    primero = _documento(_resultado(numero="A-1", ibl=Decimal("1000")))
    segundo = _documento(_resultado(numero="A-2", ibl=Decimal("1200")))

    filas, issues = merge_document_rows([primero, segundo])

    assert len(filas) == 2
    conflicto = next(
        issue for issue in issues if issue.code is ExtractionIssueCode.MULTI_PERIOD_CONFLICT
    )
    assert conflicto.severity is IssueSeverity.REVIEW_REQUIRED
    assert "1000" in conflicto.message
    assert "1200" in conflicto.message


def test_periodos_solapados_entre_documentos_advierten() -> None:
    primero = _documento(
        _resultado(numero="A-1", inicio=date(1984, 1, 1), fin=date(1984, 6, 30))
    )
    segundo = _documento(
        _resultado(numero="A-2", inicio=date(1984, 3, 1), fin=date(1984, 12, 31))
    )

    _filas, issues = merge_document_rows([primero, segundo])

    solape = next(
        issue for issue in issues if issue.code is ExtractionIssueCode.MULTI_PERIOD_OVERLAP
    )
    assert solape.severity is IssueSeverity.REVIEW_REQUIRED
    assert "dos veces" in solape.message


def test_merge_resultados_anota_procedencia_y_usa_la_peor_confianza() -> None:
    primero = _documento(_resultado(numero="A-1", inicio=date(1984, 1, 1), fin=date(1984, 12, 31)))
    segundo = _documento(
        _resultado(numero="A-2", inicio=date(1985, 1, 1), fin=date(1985, 12, 31), anio=1985)
    )
    primero = create_documento(
        CetilExtractionResult(
            **{**_campos(primero.resultado), "confidence_score": 0.9}
        )
    )
    segundo = create_documento(
        CetilExtractionResult(
            **{**_campos(segundo.resultado), "confidence_score": 0.4}
        )
    )

    merged = merge_resultados([primero, segundo])

    assert len(merged.filas_liquidables_anuales) == 2
    assert all(fila.documento_cetil for fila in merged.filas_liquidables_anuales)
    assert merged.confidence_score == 0.4
    assert merged.trabajador is not None


def test_quitar_documento_y_round_trip_del_estado() -> None:
    documentos = [
        _documento(_resultado(numero="A-1")),
        _documento(_resultado(numero="A-2", inicio=date(1985, 1, 1), fin=date(1985, 12, 31), anio=1985)),
    ]
    restaurados = documentos_from_state(documentos_to_state(documentos))

    assert [doc.documento_id for doc in restaurados] == [doc.documento_id for doc in documentos]
    assert restaurados[0].etiqueta == documentos[0].etiqueta

    quedan = remove_documento(restaurados, documentos[0].documento_id)

    assert [doc.documento_id for doc in quedan] == [documentos[1].documento_id]


def test_etiqueta_no_contiene_datos_personales() -> None:
    documento = _documento(
        _resultado(numero="CETIL-77"),
        filename="cetil.pdf",
    )

    assert "CETIL-77" in documento.etiqueta
    assert "PERSONA DE PRUEBA" not in documento.etiqueta
    assert "123456" not in documento.etiqueta


def _campos(resultado: CetilExtractionResult) -> dict:
    return {
        "metadata": resultado.metadata,
        "trabajador": resultado.trabajador,
        "entidad_empleadora": resultado.entidad_empleadora,
        "entidad_certificadora": resultado.entidad_certificadora,
        "periodos_certificados": resultado.periodos_certificados,
        "factores_salariales": resultado.factores_salariales,
        "filas_liquidables_anuales": resultado.filas_liquidables_anuales,
        "advertencias": resultado.advertencias,
        "issues": resultado.issues,
        "texto_paginas": resultado.texto_paginas,
    }
