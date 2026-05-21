from __future__ import annotations

from datetime import date
from decimal import Decimal

from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    CetilFactorSalarial,
    CetilPeriodoCertificado,
)
from app_indemnizaciones.services.period_normalizer import (
    cetil_extraction_to_period_rows,
    cetil_period_to_ui_row,
    normalize_cetil_to_annual_periods,
    normalize_period_row,
    parse_ibl_decimal,
    period_row_to_model,
    split_period_by_calendar_year,
)
from app_indemnizaciones.utils.validators import validate_period_row


def test_parse_ibl_decimal_acepta_formatos_comunes():
    assert parse_ibl_decimal("14000") == Decimal("14000")
    assert parse_ibl_decimal("14,000") == Decimal("14000")
    assert parse_ibl_decimal("14.000") == Decimal("14000")
    assert parse_ibl_decimal("14000.00") == Decimal("14000.00")


def test_normalize_period_row_completa_columnas_canónicas():
    row = normalize_period_row({"fecha_inicio": "2020-01-01", "ibl_reportado": "14.000"})

    assert row["id"]
    assert row["fecha_inicio"] == "2020-01-01"
    assert row["fecha_fin"] == ""
    assert row["ibl_reportado"] == "14000"
    assert row["fuente"] == "manual"
    assert row["estado_validacion"] == ""
    assert row["errores"] == ""


def test_conversion_fila_ui_a_modelo_periodo_laborado():
    model = period_row_to_model(
        {
            "id": "abc123",
            "fecha_inicio": "2020-01-01",
            "fecha_fin": "2020-12-31",
            "ibl_reportado": "14.000",
            "cargo": "Analista",
            "entidad": "Entidad",
            "fuente": "manual",
            "observaciones": "",
        }
    )

    assert model.fecha_inicio == date(2020, 1, 1)
    assert model.fecha_fin == date(2020, 12, 31)
    assert model.ibl_reportado == Decimal("14000")
    assert model.cargo == "Analista"
    assert model.entidad == "Entidad"
    assert model.fuente == "manual"


def test_convierte_periodo_cetil_a_fila_ui():
    row = cetil_period_to_ui_row(
        CetilPeriodoCertificado(
            fecha_desde=date(1983, 9, 29),
            fecha_hasta=date(1984, 11, 30),
            cargo="Auxiliar",
            entidad_responsable="Entidad",
            fuente_pagina=1,
            raw_text="periodo",
        )
    )

    assert row["fecha_inicio"] == "1983-09-29"
    assert row["fecha_fin"] == "1984-11-30"
    assert row["fuente"] == "cetil"
    assert row["anio"] == "1983"


def test_cetil_conserva_cargo_y_entidad():
    row = cetil_period_to_ui_row(
        CetilPeriodoCertificado(
            fecha_desde=date(1983, 9, 29),
            fecha_hasta=date(1984, 11, 30),
            cargo="Auxiliar Administrativo",
            entidad_responsable="Entidad Empleadora",
        )
    )

    assert row["cargo"] == "Auxiliar Administrativo"
    assert row["entidad"] == "Entidad Empleadora"


def test_ibl_cetil_vacio_bloquea_al_validar():
    row = cetil_period_to_ui_row(
        CetilPeriodoCertificado(
            fecha_desde=date(1983, 9, 29),
            fecha_hasta=date(1984, 11, 30),
            cargo="Auxiliar",
            entidad_responsable="Entidad",
        )
    )
    validated = validate_period_row(row)

    assert validated["estado_validacion"] == "ERROR"
    assert "IBL reportado requerido" in validated["errores"]


def test_cetil_no_genera_salarios_en_cero():
    rows = cetil_extraction_to_period_rows(
        CetilExtractionResult(
            periodos_certificados=[
                CetilPeriodoCertificado(
                    fecha_desde=date(1983, 9, 29),
                    fecha_hasta=date(1984, 11, 30),
                )
            ]
        )
    )

    assert rows[0]["ibl_reportado"] == ""
    assert rows[0]["ibl_reportado"] != "0"


def test_split_period_by_calendar_year_mismo_anio():
    segments = split_period_by_calendar_year(date(1983, 9, 29), date(1983, 12, 31))

    assert segments == [
        {"anio": 1983, "fecha_inicio": date(1983, 9, 29), "fecha_fin": date(1983, 12, 31)}
    ]


def test_split_period_by_calendar_year_dos_anios():
    segments = split_period_by_calendar_year(date(1983, 9, 29), date(1984, 11, 30))

    assert segments == [
        {"anio": 1983, "fecha_inicio": date(1983, 9, 29), "fecha_fin": date(1983, 12, 31)},
        {"anio": 1984, "fecha_inicio": date(1984, 1, 1), "fecha_fin": date(1984, 11, 30)},
    ]


def test_split_period_by_calendar_year_multiple_hasta_1988():
    segments = split_period_by_calendar_year(date(1983, 9, 29), date(1988, 1, 17))

    assert segments[0]["fecha_inicio"] == date(1983, 9, 29)
    assert segments[-1] == {
        "anio": 1988,
        "fecha_inicio": date(1988, 1, 1),
        "fecha_fin": date(1988, 1, 17),
    }
    assert [segment["anio"] for segment in segments] == [1983, 1984, 1985, 1986, 1987, 1988]


def test_consolidacion_segmentos_contiguos_mismo_anio():
    rows, warnings = normalize_cetil_to_annual_periods(
        CetilExtractionResult(
            periodos_certificados=[
                _periodo(date(1984, 1, 1), date(1984, 6, 30)),
                _periodo(date(1984, 7, 1), date(1984, 12, 31)),
            ],
            factores_salariales=[_factor(1984, Decimal("11298"))],
        )
    )

    assert len(rows) == 1
    assert rows[0].fecha_inicio == date(1984, 1, 1)
    assert rows[0].fecha_fin == date(1984, 12, 31)
    assert not any("brecha real" in warning for warning in warnings)


def test_consolidacion_segmentos_con_brecha_se_mantienen_separados():
    rows, warnings = normalize_cetil_to_annual_periods(
        CetilExtractionResult(
            periodos_certificados=[
                _periodo(date(1984, 1, 1), date(1984, 6, 30)),
                _periodo(date(1984, 7, 2), date(1984, 12, 31)),
            ],
            factores_salariales=[_factor(1984, Decimal("11298"))],
        )
    )

    assert len(rows) == 2
    assert any("brecha real" in warning for warning in warnings)


def test_anualizacion_excel_base_y_ibl_por_anio():
    rows, warnings = normalize_cetil_to_annual_periods(
        CetilExtractionResult(
            periodos_certificados=[
                _periodo(date(1983, 9, 29), date(1984, 11, 30)),
                _periodo(date(1984, 12, 1), date(1987, 11, 6)),
                _periodo(date(1987, 11, 7), date(1988, 1, 17)),
            ],
            factores_salariales=[
                _factor(1983, Decimal("14000")),
                _factor(1984, Decimal("11298")),
                _factor(1985, Decimal("16500")),
                _factor(1986, Decimal("16850")),
                _factor(1987, Decimal("20510")),
                _factor(1988, Decimal("20510")),
            ],
        )
    )

    assert [(row.anio, row.fecha_inicio, row.fecha_fin, row.ibl_reportado) for row in rows] == [
        (1983, date(1983, 9, 29), date(1983, 12, 31), Decimal("14000")),
        (1984, date(1984, 1, 1), date(1984, 12, 31), Decimal("11298")),
        (1985, date(1985, 1, 1), date(1985, 12, 31), Decimal("16500")),
        (1986, date(1986, 1, 1), date(1986, 12, 31), Decimal("16850")),
        (1987, date(1987, 1, 1), date(1987, 11, 7), Decimal("20510")),
        (1988, date(1988, 1, 1), date(1988, 1, 17), Decimal("20510")),
    ]
    assert any("anualización tipo Excel base" in warning for warning in warnings)


def test_filas_cetil_anuales_quedan_con_fuente_anio_y_validacion():
    rows = cetil_extraction_to_period_rows(
        CetilExtractionResult(
            periodos_certificados=[
                _periodo(date(1983, 9, 29), date(1983, 12, 31)),
            ]
        )
    )
    validated = validate_period_row(rows[0])

    assert rows[0]["fuente"] == "cetil"
    assert rows[0]["anio"] == "1983"
    assert validated["estado_validacion"] == "ERROR"
    assert "IBL reportado requerido" in validated["errores"]


def _periodo(fecha_desde: date, fecha_hasta: date) -> CetilPeriodoCertificado:
    return CetilPeriodoCertificado(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        cargo="Cargo",
        entidad_responsable="Entidad",
    )


def _factor(anio: int, value: Decimal) -> CetilFactorSalarial:
    return CetilFactorSalarial(
        anio=anio,
        concepto="ASIGNACIÓN BÁSICA MENSUAL",
        valores_mensuales={},
        valores_encontrados=[value] * 12,
        asignacion_basica_mensual=value,
        ibl_sugerido=value,
    )
