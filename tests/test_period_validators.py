from __future__ import annotations

from app_indemnizaciones.utils.validators import validate_period_row, validate_period_rows


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "id": "abc123",
        "fecha_inicio": "2020-01-01",
        "fecha_fin": "2020-12-31",
        "ibl_reportado": "14000",
        "cargo": "Analista",
        "entidad": "Entidad",
        "fuente": "manual",
        "observaciones": "",
    }
    base.update(overrides)
    return base


def test_fila_valida():
    result = validate_period_row(_row())

    assert result["estado_validacion"] == "OK"
    assert result["errores"] == ""


def test_fecha_inicio_vacia():
    result = validate_period_row(_row(fecha_inicio=""))

    assert result["estado_validacion"] == "ERROR"
    assert "fecha_inicio obligatoria" in result["errores"]


def test_fecha_fin_vacia():
    result = validate_period_row(_row(fecha_fin=""))

    assert result["estado_validacion"] == "ERROR"
    assert "fecha_fin obligatoria" in result["errores"]


def test_fecha_invalida():
    result = validate_period_row(_row(fecha_inicio="2020-15-01"))

    assert result["estado_validacion"] == "ERROR"
    assert "fecha_inicio debe tener formato AAAA-MM-DD" in result["errores"]


def test_fecha_inicio_posterior_a_fecha_fin():
    result = validate_period_row(_row(fecha_inicio="2021-01-01", fecha_fin="2020-01-01"))

    assert result["estado_validacion"] == "ERROR"
    assert "fecha_inicio no puede ser posterior a fecha_fin" in result["errores"]


def test_ibl_vacio():
    result = validate_period_row(_row(ibl_reportado=""))

    assert result["estado_validacion"] == "ERROR"
    assert "IBL reportado requerido" in result["errores"]


def test_ibl_no_numerico():
    result = validate_period_row(_row(ibl_reportado="abc"))

    assert result["estado_validacion"] == "ERROR"
    assert "ibl_reportado debe ser numérico" in result["errores"]


def test_ibl_menor_o_igual_a_cero():
    result = validate_period_row(_row(ibl_reportado="0"))

    assert result["estado_validacion"] == "ERROR"
    assert "ibl_reportado debe ser mayor que cero" in result["errores"]


def test_fuente_invalida():
    result = validate_period_row(_row(fuente="ocr"))

    assert result["estado_validacion"] == "ERROR"
    assert "fuente debe ser manual, cetil o importado" in result["errores"]


def test_cargo_y_entidad_vacios_generan_advertencia_no_error():
    result = validate_period_row(_row(cargo="", entidad=""))

    assert result["estado_validacion"] == "ADVERTENCIA"
    assert "cargo vacío" in result["errores"]
    assert "entidad vacía" in result["errores"]


def test_duplicado_exacto_genera_advertencia():
    rows = validate_period_rows([_row(id="a"), _row(id="b")])

    assert [row["estado_validacion"] for row in rows] == ["ADVERTENCIA", "ADVERTENCIA"]
    assert all("posible duplicado" in row["errores"] for row in rows)


def test_solapamiento_genera_advertencia():
    rows = validate_period_rows(
        [
            _row(id="a", fecha_inicio="2020-01-01", fecha_fin="2020-06-30"),
            _row(id="b", fecha_inicio="2020-06-01", fecha_fin="2020-12-31", ibl_reportado="15000"),
        ]
    )

    assert [row["estado_validacion"] for row in rows] == ["ADVERTENCIA", "ADVERTENCIA"]
    assert all("posible solapamiento" in row["errores"] for row in rows)
