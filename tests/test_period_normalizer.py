from __future__ import annotations

from datetime import date
from decimal import Decimal

from app_indemnizaciones.services.cetil_models import CetilExtractionResult, CetilPeriodoCertificado
from app_indemnizaciones.services.period_normalizer import (
    cetil_extraction_to_period_rows,
    cetil_period_to_ui_row,
    normalize_period_row,
    parse_ibl_decimal,
    period_row_to_model,
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
