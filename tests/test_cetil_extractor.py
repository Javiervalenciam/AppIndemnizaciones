from __future__ import annotations

from decimal import Decimal

from app_indemnizaciones.services.cetil_extractor import CetilExtractor
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
    assert result.entidad_empleadora.nombre_entidad_empleadora == "Alcaldia Municipal De Prueba"
    assert result.entidad_empleadora.nit_entidad_empleadora == "8001234567"
    assert (
        result.entidad_empleadora.fecha_vigencia_sistema_general_pensiones.isoformat()
        == "1994-04-01"
    )


def test_detecta_periodos_con_fechas_dd_mm_aaaa():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert len(result.periodos_certificados) == 2
    assert result.periodos_certificados[0].raw_text.startswith("29-09-1983")
    assert result.periodos_certificados[0].cargo == "AUXILIAR ADMINISTRATIVO"
    assert result.periodos_certificados[0].entidad_responsable == "Entidad Uno"


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


def test_parse_money_maneja_formatos_requeridos():
    assert parse_money("11,298.00") == Decimal("11298.00")
    assert parse_money("16,500.00") == Decimal("16500.00")
    assert parse_money("16.500,00") == Decimal("16500.00")
    assert parse_money("14,000") == Decimal("14000")
    assert parse_money("14.000") == Decimal("14000")
    assert parse_money("$14.000") == Decimal("14000")
    assert parse_money("0.00") == Decimal("0.00")
    assert parse_money("") is None


def test_si_faltan_datos_genera_advertencias_y_no_inventa_valores():
    result = CetilExtractor().extract_from_pages({1: "DATOS DEL EMPLEADO\nSIN TABLAS"})

    assert result.periodos_certificados == []
    assert result.factores_salariales == []
    assert "No se detectaron periodos certificados." in result.advertencias
    assert "No se detectaron bloques de factores salariales." in result.advertencias
