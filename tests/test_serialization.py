from __future__ import annotations

from datetime import date
from decimal import Decimal

from app_indemnizaciones.domain.models import ResultadoLiquidacion, ResultadoPeriodo
from app_indemnizaciones.services.serialization import (
    deserialize_periods,
    resultado_from_dict,
    resultado_to_dict,
    serialize_periods,
)


def _resultado() -> ResultadoLiquidacion:
    return ResultadoLiquidacion(
        periodos=[
            ResultadoPeriodo(
                fecha_inicio=date(1983, 1, 1),
                fecha_fin=date(1983, 12, 31),
                ibl_reportado=Decimal("1000"),
                dias=365,
                semanas=Decimal("52.14285714285714285714285714"),
                periodo_ipc_inicial="PROMEDIO ANUAL 1983",
                ipc_inicial=Decimal("15"),
                periodo_ipc_actual="2026-04",
                ipc_actual=Decimal("200"),
                ibc_actualizado=Decimal("13333.33"),
                ibc_semanal_actualizado=Decimal("3068.66"),
                anio=1983,
                documento_cetil="CETIL A-1 · 2024-01-10",
            )
        ],
        total_dias=365,
        sc=Decimal("52.14285714285714285714285714"),
        sbc=Decimal("3068.66"),
        ppc=Decimal("0.0227"),
        isv=Decimal("35.55"),
        fecha_liquidacion=date(2026, 4, 30),
        ipc_actual_periodo="2026-04",
        ipc_actual_fuente="fecha_liquidacion",
        advertencias=("Advertencia de prueba.",),
    )


def test_serializacion_conserva_fecha_liquidacion_e_ipc_actual():
    resultado = _resultado()

    restored = resultado_from_dict(resultado_to_dict(resultado))

    assert restored.fecha_liquidacion == date(2026, 4, 30)
    assert restored.ipc_actual_periodo == "2026-04"
    assert restored.ipc_actual_fuente == "fecha_liquidacion"
    assert restored.advertencias == ("Advertencia de prueba.",)
    assert restored.periodos[0].dias == 365
    assert restored.periodos[0].documento_cetil == "CETIL A-1 · 2024-01-10"


def test_serializacion_sin_fecha_liquidacion_es_compatible():
    payload = resultado_to_dict(_resultado())
    payload["fecha_liquidacion"] = None

    restored = resultado_from_dict(payload)

    assert restored.fecha_liquidacion is None


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
