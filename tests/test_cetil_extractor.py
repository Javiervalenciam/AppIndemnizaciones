from __future__ import annotations

from decimal import Decimal

from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from app_indemnizaciones.utils.money import parse_money


def _sample_text() -> str:
    return """
DATOS DEL EMPLEADO
TIPO DOCUMENTO CC NUMERO 123456
PRIMER APELLIDO PRUEBA
SEGUNDO APELLIDO DATOS
PRIMER NOMBRE ANA
SEGUNDO NOMBRE MARIA
FECHA DE NACIMIENTO 01-02-1960

PERIODOS CERTIFICADOS
29-09-1983 30-11-1984 LEGAL Y REGLAMENTARIA PUBLICO AUXILIAR ADMINISTRATIVO ENTIDAD RESPONSABLE: ENTIDAD UNO 421
01-12-1984 06-11-1987 LEGAL Y REGLAMENTARIA PUBLICO PROFESIONAL ENTIDAD RESPONSABLE: ENTIDAD DOS 1050

FACTORES SALARIALES 1983
ASIGNACIÓN BÁSICA MENSUAL 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 11,298.00 16,500.00 16,500.00 16,500.00 16,500.00
Total Devengado 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00 467,000.00 467,000.00 467,000.00 467,000.00
"""


def test_detecta_periodos_con_fechas_dd_mm_aaaa():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})

    assert len(result.periodos_certificados) == 2
    assert result.periodos_certificados[0].raw_text.startswith("29-09-1983")


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


def test_detecta_valores_monetarios_total_devengado():
    result = CetilExtractor().extract_from_pages({1: _sample_text()})
    total = next(factor for factor in result.factores_salariales if factor.concepto == "Total Devengado")

    assert total.valores_mensuales["enero"] == Decimal("0.00")
    assert total.total_devengado_mensual["septiembre"] == Decimal("467000.00")


def test_parse_money_maneja_formatos_requeridos():
    assert parse_money("11,298.00") == Decimal("11298.00")
    assert parse_money("16,500.00") == Decimal("16500.00")
    assert parse_money("16.500,00") == Decimal("16500.00")
    assert parse_money("0.00") == Decimal("0.00")
    assert parse_money("") is None


def test_si_faltan_datos_genera_advertencias_y_no_inventa_valores():
    result = CetilExtractor().extract_from_pages({1: "DATOS DEL EMPLEADO\nSIN TABLAS"})

    assert result.periodos_certificados == []
    assert result.factores_salariales == []
    assert "No se detectaron periodos certificados." in result.advertencias
    assert "No se detectaron bloques de factores salariales." in result.advertencias
