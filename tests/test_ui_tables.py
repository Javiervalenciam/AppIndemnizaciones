from __future__ import annotations

from app_indemnizaciones.ui.tables import PERIODOS_COLUMNS, build_periodos_table


def test_tabla_revision_solo_permite_editar_campos_manual_revisables():
    editable_ids = {column["id"] for column in PERIODOS_COLUMNS if column.get("editable")}

    assert editable_ids == {"fecha_inicio", "fecha_fin", "ibl_reportado", "cargo", "entidad"}


def test_tabla_revision_no_expone_columnas_calculadas_editables():
    column_ids = {column["id"] for column in PERIODOS_COLUMNS}

    assert "dias" not in column_ids
    assert "semanas" not in column_ids
    assert "porcentaje_aplicacion" not in column_ids
    assert "ipc_inicial" not in column_ids
    assert "ipc_actual" not in column_ids
    assert "ibc_actualizado" not in column_ids
    assert "ibc_semanal_actualizado" not in column_ids


def test_tabla_revision_bloquea_edicion_global_y_oculta_ids_tecnicos():
    table = build_periodos_table()

    assert table.editable is False
    assert table.hidden_columns == ["id", "fuente", "observaciones"]
