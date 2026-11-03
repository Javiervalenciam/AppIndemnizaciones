from __future__ import annotations

from decimal import Decimal

from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from app_indemnizaciones.services.cetil_models import (
    ExtractionIssueCode,
    cetil_result_from_dict,
    cetil_result_to_dict,
)

_MONTHS_LINE = (
    "ASIGNACIÓN BÁSICA MENSUAL "
    + " ".join(["1,000.00"] * 12)
)
_TOTAL_LINE = "Total Devengado " + " ".join(["1,000.00"] * 12)


def _salary_text(assignment_line: str, total_line: str = _TOTAL_LINE) -> str:
    return f"""
CERTIFICACIÓN ELECTRÓNICA DE TIEMPOS LABORADOS
PERIODOS CERTIFICADOS
01-01-1980 31-12-1980 LABORAL PÚBLICO AUXILIAR ENTIDAD RESPONSABLE: MUNICIPIO DE PRUEBA 0
FACTORES SALARIALES 1980
{assignment_line}
{total_line}
"""


def _factor(result, concepto: str):
    for factor in result.factores_salariales:
        if factor.concepto == concepto:
            return factor
    raise AssertionError(f"No factor for {concepto}")


def test_concepto_con_variante_sin_tildes_se_reconoce():
    result = CetilExtractor().extract_from_pages(
        {1: _salary_text("ASIGNACION BASICA MENSUAL " + " ".join(["2,000.00"] * 12))}
    )

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.ibl_sugerido == Decimal("2000.00")
    assert factor.ibl_metodo == "asignacion_basica_mensual"


def test_concepto_variante_sueldo_basico_se_reconoce():
    result = CetilExtractor().extract_from_pages(
        {1: _salary_text("Sueldo Básico " + " ".join(["3,000.00"] * 12))}
    )

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.ibl_sugerido == Decimal("3000.00")


def test_c_ibc_se_registra_por_mes():
    line = (
        "ASIGNACIÓN BÁSICA MENSUAL "
        + " ".join(
            [f"{1000 + index * 100}.00 {'S' if index % 2 == 0 else 'N'}" for index in range(12)]
        )
    )
    result = CetilExtractor().extract_from_pages({1: _salary_text(line)})

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.c_ibc_mensual["enero"] is True
    assert factor.c_ibc_mensual["febrero"] is False
    assert factor.c_ibc_mensual["diciembre"] is False


def test_mes_sin_marca_c_ibc_queda_en_none_y_no_en_false():
    result = CetilExtractor().extract_from_pages({1: _salary_text(_MONTHS_LINE)})

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert set(factor.c_ibc_mensual.values()) == {None}


def test_ibl_incluye_metodo_y_evidencia_trazable():
    result = CetilExtractor().extract_from_pages({1: _salary_text(_MONTHS_LINE)})

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.ibl_metodo == "asignacion_basica_mensual"
    assert "valor más frecuente" in (factor.ibl_evidencia or "")
    assert factor.ibl_requiere_revision is False


def test_mes_con_salario_fuera_del_ibc_exige_revision():
    line = (
        "ASIGNACIÓN BÁSICA MENSUAL "
        + " ".join([f"1,000.00 {'N' if index == 0 else 'S'}" for index in range(12)])
    )
    result = CetilExtractor().extract_from_pages({1: _salary_text(line)})

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.ibl_requiere_revision is True
    assert "fuera del IBC: enero" in (factor.ibl_evidencia or "")


def test_mes_sin_salario_fuera_del_ibc_no_exige_revision():
    line = "ASIGNACIÓN BÁSICA MENSUAL 0.00 N " + " ".join(
        [f"1,000.00 {'S' if index < 11 else 'N'}" for index in range(11)]
    )
    result = CetilExtractor().extract_from_pages({1: _salary_text(line)})

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.ibl_requiere_revision is False


def test_ibl_cae_a_total_devengado_si_falta_asignacion():
    result = CetilExtractor().extract_from_pages(
        {1: _salary_text("Sin concepto reconocible", _TOTAL_LINE)}
    )

    factor = _factor(result, "Total Devengado")
    assert factor.ibl_sugerido == Decimal("1000.00")
    assert factor.ibl_metodo == "total_devengado"


def test_empate_de_valores_marca_ibl_manual_y_emite_incidencia():
    line = "ASIGNACIÓN BÁSICA MENSUAL " + " ".join(
        ["1,000.00"] * 6 + ["2,000.00"] * 6
    )
    result = CetilExtractor().extract_from_pages({1: _salary_text(line)})

    factor = _factor(result, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.ibl_sugerido is None
    assert factor.ibl_metodo == "manual"
    assert factor.ibl_requiere_revision is True
    assert any(issue.code is ExtractionIssueCode.IBL_AMBIGUOUS for issue in result.issues)


def test_filas_anuales_heredan_metodo_y_evidencia_del_ibl():
    result = CetilExtractor().extract_from_pages({1: _salary_text(_MONTHS_LINE)})

    row = result.filas_liquidables_anuales[0]
    assert row.ibl_reportado == Decimal("1000.00")
    assert row.ibl_metodo == "asignacion_basica_mensual"
    assert row.ibl_evidencia
    assert row.ibl_requiere_revision is False


def test_serializacion_conserva_c_ibc_metodo_y_evidencia():
    line = (
        "ASIGNACIÓN BÁSICA MENSUAL "
        + " ".join([f"1,000.00 {'S' if index == 0 else 'N'}" for index in range(12)])
    )
    result = CetilExtractor().extract_from_pages({1: _salary_text(line)})
    restored = cetil_result_from_dict(cetil_result_to_dict(result))

    factor = _factor(restored, "ASIGNACIÓN BÁSICA MENSUAL")
    assert factor.c_ibc_mensual["enero"] is True
    assert factor.c_ibc_mensual["febrero"] is False
    assert factor.ibl_metodo == "asignacion_basica_mensual"
    assert factor.ibl_evidencia
    assert factor.ibl_requiere_revision is True
    row = restored.filas_liquidables_anuales[0]
    assert row.ibl_metodo == "asignacion_basica_mensual"
    assert row.ibl_requiere_revision is True
