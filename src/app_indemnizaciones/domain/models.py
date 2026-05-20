from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Trabajador:
    nombre: str
    documento: str
    fecha_nacimiento: date | None = None


@dataclass(frozen=True)
class PeriodoLaborado:
    fecha_inicio: date
    fecha_fin: date
    ibl_reportado: Decimal
    anio: int | None = None
    cargo: str | None = None
    entidad: str | None = None
    fuente: str | None = None


@dataclass(frozen=True)
class IpcRegistro:
    periodo: str  # YYYY-MM
    fecha: date
    indice: Decimal


@dataclass(frozen=True)
class IpcPair:
    periodo_inicial: str
    ipc_inicial: Decimal
    periodo_actual: str
    ipc_actual: Decimal


@dataclass(frozen=True)
class ResultadoPeriodo:
    fecha_inicio: date
    fecha_fin: date
    ibl_reportado: Decimal
    dias: int
    semanas: Decimal
    periodo_ipc_inicial: str
    ipc_inicial: Decimal
    periodo_ipc_actual: str
    ipc_actual: Decimal
    ibc_actualizado: Decimal
    ibc_semanal_actualizado: Decimal
    anio: int | None = None
    ipc_inicial_origen: str | None = None
    ipc_meses_usados: int | None = None
    advertencias_ipc: tuple[str, ...] = ()
    cargo: str | None = None
    entidad: str | None = None


@dataclass(frozen=True)
class ResultadoLiquidacion:
    periodos: list[ResultadoPeriodo]
    total_dias: int
    sc: Decimal
    sbc: Decimal
    ppc: Decimal
    isv: Decimal
