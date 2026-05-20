"""
Serialización de `ResultadoLiquidacion` para almacenamiento en `dcc.Store`.

`dcc.Store` solo admite valores JSON-serializables. Este módulo convierte
los objetos del dominio a/desde dicts planos sin perder precisión usando
representaciones string para `Decimal` y ISO 8601 para `date`.

No realiza cálculos: rehidratar un dict y volver a serializarlo debe
producir el mismo objeto bit a bit a nivel de campos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app_indemnizaciones.domain.models import ResultadoLiquidacion, ResultadoPeriodo
from app_indemnizaciones.services.period_normalizer import normalize_period_row
from app_indemnizaciones.utils.validators import validate_period_rows


def _periodo_to_dict(row: ResultadoPeriodo) -> dict[str, Any]:
    return {
        "fecha_inicio": row.fecha_inicio.isoformat(),
        "fecha_fin": row.fecha_fin.isoformat(),
        "ibl_reportado": str(row.ibl_reportado),
        "dias": row.dias,
        "semanas": str(row.semanas),
        "periodo_ipc_inicial": row.periodo_ipc_inicial,
        "ipc_inicial": str(row.ipc_inicial),
        "periodo_ipc_actual": row.periodo_ipc_actual,
        "ipc_actual": str(row.ipc_actual),
        "ibc_actualizado": str(row.ibc_actualizado),
        "ibc_semanal_actualizado": str(row.ibc_semanal_actualizado),
        "cargo": row.cargo,
        "entidad": row.entidad,
    }


def _periodo_from_dict(data: dict[str, Any]) -> ResultadoPeriodo:
    return ResultadoPeriodo(
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]),
        ibl_reportado=Decimal(data["ibl_reportado"]),
        dias=int(data["dias"]),
        semanas=Decimal(data["semanas"]),
        periodo_ipc_inicial=data["periodo_ipc_inicial"],
        ipc_inicial=Decimal(data["ipc_inicial"]),
        periodo_ipc_actual=data["periodo_ipc_actual"],
        ipc_actual=Decimal(data["ipc_actual"]),
        ibc_actualizado=Decimal(data["ibc_actualizado"]),
        ibc_semanal_actualizado=Decimal(data["ibc_semanal_actualizado"]),
        cargo=data.get("cargo"),
        entidad=data.get("entidad"),
    )


def resultado_to_dict(resultado: ResultadoLiquidacion) -> dict[str, Any]:
    return {
        "periodos": [_periodo_to_dict(row) for row in resultado.periodos],
        "total_dias": resultado.total_dias,
        "sc": str(resultado.sc),
        "sbc": str(resultado.sbc),
        "ppc": str(resultado.ppc),
        "isv": str(resultado.isv),
    }


def resultado_from_dict(data: dict[str, Any]) -> ResultadoLiquidacion:
    return ResultadoLiquidacion(
        periodos=[_periodo_from_dict(row) for row in data["periodos"]],
        total_dias=int(data["total_dias"]),
        sc=Decimal(data["sc"]),
        sbc=Decimal(data["sbc"]),
        ppc=Decimal(data["ppc"]),
        isv=Decimal(data["isv"]),
    )


def serialize_periods(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    return validate_period_rows([normalize_period_row(row) for row in rows or []])


def deserialize_periods(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    return validate_period_rows([normalize_period_row(row) for row in rows or []])
