from __future__ import annotations

from decimal import Decimal

from app_indemnizaciones.services.cetil_extractor import (
    CetilExtractor,
    extract_salary_blocks_across_pages,
)
from app_indemnizaciones.services.cetil_models import cetil_result_from_dict, cetil_result_to_dict
from app_indemnizaciones.utils.money import parse_money


def _sample_text() -> str:
    return """
CERTIFICACIÓN ELECTRÓNICA DE TIEMPOS LABORADOS CETIL
CETIL No. 201912800099263000890001
Ciudad y fecha de expedición: SARDINATA, Diciembre 5 de 2019

DATOS DEL EMPLEADO
Tipo de Documento: C
Documento: 5,499,027
PRIMER APELLIDO PRUEBA
SEGUNDO APELLIDO DATOS
PRIMER NOMBRE ANA
SEGUNDO NOMBRE MARIA
FECHA DE NACIMIENTO Febrero 12 de 1964

DATOS DE LA ENTIDAD EMPLEADORA
Nombre entidad empleadora: ALCALDIA MUNICIPAL DE PRUEBA
NIT: 800.123.456-7
Vigencia Sistema General de Pensiones: 01/04/1994

PERIODOS CERTIFICADOS
29-09-1983 30-11-1984 LEGAL Y REGLAMENTARIA PUBLICO AUXILIAR ADMINISTRATIVO ENTIDAD RESPONSABLE: ENTIDAD UNO 421
01-12-1984 06-11-1987 LEGAL Y REGLAMENTARIA PUBLICO PROFESIONAL ENTIDAD RESPONSABLE: ENTIDAD DOS 1050

FACTORES SALARIALES 1983
ASIGNACIÓN BÁSICA MENSUAL 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 16,500.00 16,500.00 16,500.00 16,500.00
Total Devengado 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00 467,000.00 467,000.00 467,000.00 467,000.00
"""


def test_extract_metadata_from_text():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert result.metadata is not None
    assert result.metadata.numero_cetil == "201912800099263000890001"
    assert result.metadata.ciudad_expedicion == "SARDINATA"
    assert result.metadata.fecha_expedicion_cetil.isoformat() == "2019-12-05"


def test_extract_worker_from_text():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert result.trabajador is not None
    assert result.trabajador.tipo_documento == "C"
    assert result.trabajador.documento == "5499027"
    assert result.trabajador.fecha_nacimiento.isoformat() == "1964-02-12"
    assert result.trabajador.primer_apellido == "Prueba"
    assert result.trabajador.segundo_apellido == "Datos"
    assert result.trabajador.primer_nombre == "Ana"
    assert result.trabajador.segundo_nombre == "Maria"
    assert result.trabajador.nombre_completo == "Ana Maria Prueba Datos"
    assert result.trabajador.genero is None
    assert "No se detectó campo explícito de género en el CETIL." in result.advertencias


def test_extract_entidad_empleadora_from_text():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert result.entidad_empleadora is not None
    assert result.entidad_empleadora.nombre_entidad_empleadora == "ALCALDIA MUNICIPAL DE PRUEBA"
    assert result.entidad_empleadora.nit_entidad_empleadora == "8001234567"
    assert (
        result.entidad_empleadora.fecha_vigencia_sistema_general_pensiones.isoformat()
        == "1994-04-01"
    )


def test_detecta_periodos_con_fechas_dd_mm_aaaa():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert len(result.periodos_certificados) == 2
    assert result.periodos_certificados[0].raw_text.startswith("29-09-1983")
    assert result.periodos_certificados[0].cargo == "Auxiliar Administrativo"
    assert result.periodos_certificados[0].entidad_responsable == "Entidad Uno"


def test_worker_name_does_not_include_labels():
    result = CetilExtractor().extract_from_pages(
        {
            1: """
DATOS DE LA ENTIDAD EMPLEADORA
Nombre: MUNICIPIO DE BOCHALEMA Nit: 890,505,662 Junio 30 de 1995
el Sistema General de Pensiones:
DATOS DEL EMPLEADO
Tipo de Documento: C Documento: 88,152,324 Fecha de Nacimiento: Agosto 25 de 1964
Primer Apellido: IBARRA Segundo Apellido: CAMPOS Primer Nombre: HUGO Segundo Nombre:
PERIODOS CERTIFICADOS
14-04-1993 31-05-1995 LABORAL PÚBLICO Coordinador SI SI SI MUNICIPIO DE BOCHALEMA 0 NO SI
FACTORES SALARIALES 1993
ASIGNACIÓN BÁSICA MENSUAL 104,490.00 104,490.00
"""
        }
    )

    assert result.trabajador is not None
    assert result.trabajador.nombre_completo == "Hugo Ibarra Campos"
    forbidden = [
        "Periodos Certificados",
        "Primer Nombre",
        "Segundo Nombre",
        "Segundo Apellido",
        "Documento",
    ]
    assert all(label not in result.trabajador.nombre_completo for label in forbidden)


def test_tipo_documento_clean():
    result = CetilExtractor().extract_from_pages(
        {
            1: """
DATOS DEL EMPLEADO
Tipo de Documento: C DOCUMENTO: 88,152,324 Fecha de Nacimiento: Agosto 25 de 1964
Primer Apellido: IBARRA Segundo Apellido: CAMPOS Primer Nombre: HUGO Segundo Nombre:
PERIODOS CERTIFICADOS
"""
        }
    )

    assert result.trabajador is not None
    assert result.trabajador.tipo_documento == "C"


def test_employer_name_not_confused_with_pension_label():
    result = CetilExtractor().extract_from_pages(
        {
            1: """
DATOS DE LA ENTIDAD EMPLEADORA
Fecha en que entró en vigencia
Nombre: MUNICIPIO DE BOCHALEMA Nit: 890,505,662 Junio 30 de 1995
el Sistema General de Pensiones:
DATOS DEL EMPLEADO
Documento: 88,152,324
PERIODOS CERTIFICADOS
"""
        }
    )

    assert result.entidad_empleadora is not None
    assert result.entidad_empleadora.nombre_entidad_empleadora == "MUNICIPIO DE BOCHALEMA"
    assert result.entidad_empleadora.nombre_entidad_empleadora != "El Sistema General De Pensiones"


def test_period_row_splits_cargo_and_entity():
    result = CetilExtractor().extract_from_pages(
        {
            1: """
PERIODOS CERTIFICADOS
14-04-1993 31-05-1995 LABORAL PÚBLICO Coordinador SI SI SI MUNICIPIO DE BOCHALEMA 0 NO SI
FACTORES SALARIALES 1993
"""
        }
    )

    assert result.periodos_certificados[0].cargo == "Coordinador"
    assert result.periodos_certificados[0].entidad_responsable == "MUNICIPIO DE BOCHALEMA"


def test_worker_card_data_serialization():
    result = CetilExtractor().extract_from_pages(
        {
            1: """
CETIL No. 20260000026131
Ciudad y fecha de expedición: BOCHALEMA, Marzo 17 de 2026
DATOS DE LA ENTIDAD EMPLEADORA
Nombre: MUNICIPIO DE BOCHALEMA Nit: 890,505,662 Junio 30 de 1995
el Sistema General de Pensiones:
DATOS DEL EMPLEADO
Tipo de Documento: C Documento: 88,152,324 Fecha de Nacimiento: Agosto 25 de 1964
Primer Apellido: IBARRA Segundo Apellido: CAMPOS Primer Nombre: HUGO Segundo Nombre:
PERIODOS CERTIFICADOS
"""
        }
    )

    restored = cetil_result_from_dict(cetil_result_to_dict(result))

    assert restored.trabajador is not None
    assert restored.trabajador.nombre_completo == "Hugo Ibarra Campos"
    assert restored.trabajador.documento == "88152324"
    assert restored.trabajador.fecha_nacimiento is not None
    assert restored.metadata is not None
    assert restored.metadata.numero_cetil == "20260000026131"
    assert restored.entidad_empleadora is not None
    assert restored.entidad_empleadora.nombre_entidad_empleadora == "MUNICIPIO DE BOCHALEMA"


def test_normaliza_fechas_a_iso():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert result.periodos_certificados[0].fecha_desde.isoformat() == "1983-09-29"
    assert result.periodos_certificados[0].fecha_hasta.isoformat() == "1984-11-30"


def test_detecta_encabezados_factores_salariales_por_anio():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert {factor.anio for factor in result.factores_salariales} == {1983}


def test_detecta_valores_monetarios_asignacion_basica_mensual():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})
    asignacion = next(
        factor for factor in result.factores_salariales if factor.concepto == "ASIGNACIÓN BÁSICA MENSUAL"
    )

    assert asignacion.valores_mensuales["enero"] == Decimal("11298.00")
    assert asignacion.valores_mensuales["septiembre"] == Decimal("16500.00")
    assert asignacion.asignacion_basica_mensual == Decimal("11298.00")
    assert asignacion.ibl_sugerido == Decimal("11298.00")


def test_ibl_sugerido_usa_valor_mas_frecuente_y_advierte_atipico():
    result = CetilExtractor().extract_from_pages(
        {
            1: """
DATOS DEL EMPLEADO
Documento: 1

PERIODOS CERTIFICADOS
29-09-1983 31-12-1983 LEGAL Y REGLAMENTARIA PUBLICO AUXILIAR ENTIDAD RESPONSABLE: ENTIDAD 92

FACTORES SALARIALES 1983
ASIGNACIÓN BÁSICA MENSUAL 467,000.00 14,000.00 14,000.00 14,000.00
"""
        }
    )
    factor = next(row for row in result.factores_salariales if row.anio == 1983)

    assert factor.ibl_sugerido == Decimal("14000.00")
    assert any("posible valor atípico" in warning for warning in result.advertencias)


def test_detecta_valores_monetarios_total_devengado():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})
    total = next(factor for factor in result.factores_salariales if factor.concepto == "Total Devengado")

    assert total.valores_mensuales["enero"] == Decimal("0.00")
    assert total.total_devengado_mensual["septiembre"] == Decimal("467000.00")


def test_salary_block_split_across_pages():
    pages_text = _split_salary_pages()

    blocks = extract_salary_blocks_across_pages(pages_text)
    result = CetilExtractor().extract_from_pages(pages_text)

    assert len(blocks) == 1
    assert blocks[0].anio == 1987
    assert blocks[0].start_page == 2
    assert blocks[0].end_page == 3
    assert "ASIGNACIÓN BÁSICA MENSUAL" in blocks[0].raw_text
    assert "Total Devengado" in blocks[0].raw_text
    factor = next(
        row
        for row in result.factores_salariales
        if row.anio == 1987 and row.concepto == "ASIGNACIÓN BÁSICA MENSUAL"
    )
    assert factor.asignacion_basica_mensual == Decimal("20510.00")
    assert factor.ibl_sugerido == Decimal("20510.00")
    assert not any("No se detectó IBL para el año 1987" in warning for warning in result.advertencias)


def test_salary_block_closes_on_next_salary_year():
    pages_text = {
        1: """
FACTORES SALARIALES 1984 (Valores en pesos)
ASIGNACIÓN BÁSICA MENSUAL MENSUAL 11,298.00 S 11,298.00 S
FACTORES SALARIALES 1985 (Valores en pesos)
ASIGNACIÓN BÁSICA MENSUAL MENSUAL 16,500.00 S 16,500.00 S
"""
    }

    blocks = extract_salary_blocks_across_pages(pages_text)

    assert [block.anio for block in blocks] == [1984, 1985]
    assert "16,500.00" not in blocks[0].raw_text
    assert "11,298.00" not in blocks[1].raw_text


def test_salary_block_closes_on_informacion_valida():
    pages_text = {
        2: """
FACTORES SALARIALES 1987 (Valores en pesos)
ASIGNACIÓN BÁSICA MENSUAL MENSUAL 20,510.00 N
INFORMACIÓN VÁLIDA ÚNICAMENTE CUANDO LA PRESTACIÓN SE FINANCIE CON BONO PENSIONAL
POSIBLE FECHA BASE
"""
    }

    blocks = extract_salary_blocks_across_pages(pages_text)

    assert len(blocks) == 1
    assert "INFORMACIÓN VÁLIDA" not in blocks[0].raw_text
    assert "POSIBLE FECHA BASE" not in blocks[0].raw_text


def test_split_salary_block_keeps_assignment_row():
    blocks = extract_salary_blocks_across_pages(_split_salary_pages())

    assert "ASIGNACIÓN BÁSICA MENSUAL" in blocks[0].raw_text
    assert "20,510.00" in blocks[0].raw_text


def test_annual_rows_get_ibl_from_split_salary_block():
    pages_text = {
        1: """
PERIODOS CERTIFICADOS
01-01-1987 31-12-1987 LABORAL PÚBLICO Coordinador SI SI SI MUNICIPIO DE BOCHALEMA 0 NO SI
""",
        **_split_salary_pages(),
    }

    result = CetilExtractor().extract_from_pages(pages_text)

    row_1987 = next(row for row in result.filas_liquidables_anuales if row.anio == 1987)
    assert row_1987.ibl_reportado == Decimal("20510.00")
    assert not any("No se detectó IBL para el año 1987" in warning for warning in result.advertencias)


def test_parse_money_maneja_formatos_requeridos():
    assert parse_money("11,298.00") == Decimal("11298.00")
    assert parse_money("16,500.00") == Decimal("16500.00")
    assert parse_money("16.500,00") == Decimal("16500.00")
    assert parse_money("14,000") == Decimal("14000")
    assert parse_money("14.000") == Decimal("14000")
    assert parse_money("$14.000") == Decimal("14000")
    assert parse_money("0.00") == Decimal("0.00")
    assert parse_money("") is None


def _split_salary_pages() -> dict[int, str]:
    return {
        2: """
FACTORES SALARIALES 1987 (Valores en pesos)
DECRETO 1158 DE 1994 Periodicidad Enero C.IBC Febrero C.IBC Marzo C.IBC Abril C.IBC Mayo C.IBC Junio C.IBC Julio C.IBC Agosto C.IBC Septiembre C.IBC Octubre C.IBC Noviembre C.IBC Diciembre C.IBC
Pag. 2
""",
        3: """
CERTIFICACIÓN ELECTRÓNICA DE TIEMPOS LABORADOS
CETIL
ASIGNACIÓN BÁSICA MENSUAL MENSUAL 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N 20,510.00 N
Total Devengado 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00 20,510.00
INFORMACIÓN VÁLIDA ÚNICAMENTE CUANDO LA PRESTACIÓN SE FINANCIE CON BONO PENSIONAL
""",
    }


def test_si_faltan_datos_genera_advertencias_y_no_inventa_valores():
    result = CetilExtractor().extract_from_pages({1: "DATOS DEL EMPLEADO\nSIN TABLAS"})

    assert result.periodos_certificados == []
    assert result.factores_salariales == []
    assert "No se detectaron periodos certificados." in result.advertencias
    assert "No se detectaron bloques de factores salariales." in result.advertencias
