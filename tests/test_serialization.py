from __future__ import annotations

from app_indemnizaciones.services.serialization import deserialize_periods, serialize_periods


def test_serializacion_deserializacion_conserva_periodos():
    rows = [
        {
            "id": "abc123",
            "fecha_inicio": "2020-01-01",
            "fecha_fin": "2020-12-31",
            "ibl_reportado": "14,000",
            "cargo": "Analista",
            "entidad": "Entidad",
            "fuente": "manual",
            "observaciones": "Revisado",
        }
    ]

    serialized = serialize_periods(rows)
    deserialized = deserialize_periods(serialized)

    assert serialized == deserialized
    assert deserialized[0]["ibl_reportado"] == "14000"
    assert deserialized[0]["estado_validacion"] == "OK"
