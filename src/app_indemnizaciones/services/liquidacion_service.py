from __future__ import annotations

from decimal import Decimal, getcontext

from app_indemnizaciones.config import MONTHLY_TO_WEEKLY_DIVISOR, CalculationConfig
from app_indemnizaciones.domain.exceptions import LiquidacionError
from app_indemnizaciones.domain.models import (
    PeriodoLaborado,
    ResultadoLiquidacion,
    ResultadoPeriodo,
)
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.utils.dates import calendar_days, commercial_360_days

getcontext().prec = 28


class LiquidacionService:
    def __init__(self, ipc_repository: IpcRepository, config: CalculationConfig | None = None) -> None:
        self.ipc_repository = ipc_repository
        self.config = config or CalculationConfig()

    def calcular(
        self,
        periodos: list[PeriodoLaborado],
        fecha_liquidacion: object | None = None,
        day_count: str | None = None,
    ) -> ResultadoLiquidacion:
        if not periodos:
            raise LiquidacionError("Debe existir al menos un periodo laborado.")

        convention = day_count or self.config.default_day_count
        resultados = [
            self._calcular_periodo(periodo, fecha_liquidacion=fecha_liquidacion, day_count=convention)
            for periodo in periodos
        ]

        total_dias = sum(row.dias for row in resultados)
        sc = Decimal(total_dias) / Decimal(7)
        # Regla vigente del Excel base: SBC es promedio aritmético simple
        # de IBC semanal actualizado. No ponderar por días sin decisión legal.
        sbc = sum((row.ibc_semanal_actualizado for row in resultados), Decimal(0)) / Decimal(
            len(resultados)
        )
        # PPC vigente para indemnización sustitutiva de vejez: 0.0227.
        # No redondear internamente; el redondeo queda para UI/exportación.
        ppc = Decimal(str(self.config.ppc))
        isv = sbc * sc * ppc

        return ResultadoLiquidacion(
            periodos=resultados,
            total_dias=total_dias,
            sc=sc,
            sbc=sbc,
            ppc=ppc,
            isv=isv,
        )

    def _calcular_periodo(
        self,
        periodo: PeriodoLaborado,
        fecha_liquidacion: object | None,
        day_count: str,
    ) -> ResultadoPeriodo:
        if periodo.fecha_fin < periodo.fecha_inicio:
            raise LiquidacionError("La fecha final del periodo no puede ser anterior a la inicial.")
        if periodo.ibl_reportado <= 0:
            raise LiquidacionError("El IBL reportado debe ser mayor que cero.")

        if day_count == "commercial_360":
            dias = commercial_360_days(periodo.fecha_inicio, periodo.fecha_fin)
        elif day_count == "calendar":
            dias = calendar_days(periodo.fecha_inicio, periodo.fecha_fin)
        else:
            raise LiquidacionError(f"Convención de días no soportada: {day_count}")

        anio = periodo.anio or periodo.fecha_inicio.year
        ipc_inicial_info = self.ipc_repository.get_annual_average_ipc_info(anio)
        ipc_actual = self.ipc_repository.get_current_ipc()
        semanas = Decimal(dias) / Decimal(7)
        ibc_actualizado = periodo.ibl_reportado * (ipc_actual.indice / ipc_inicial_info.average)
        ibc_semanal_actualizado = ibc_actualizado / MONTHLY_TO_WEEKLY_DIVISOR

        return ResultadoPeriodo(
            fecha_inicio=periodo.fecha_inicio,
            fecha_fin=periodo.fecha_fin,
            ibl_reportado=periodo.ibl_reportado,
            dias=dias,
            semanas=semanas,
            periodo_ipc_inicial=f"PROMEDIO ANUAL {anio}",
            ipc_inicial=ipc_inicial_info.average,
            periodo_ipc_actual=ipc_actual.periodo,
            ipc_actual=ipc_actual.indice,
            ibc_actualizado=ibc_actualizado,
            ibc_semanal_actualizado=ibc_semanal_actualizado,
            anio=anio,
            ipc_inicial_origen=f"PROMEDIO ANUAL {anio}",
            ipc_meses_usados=ipc_inicial_info.months_count,
            advertencias_ipc=tuple(ipc_inicial_info.warnings),
            cargo=periodo.cargo,
            entidad=periodo.entidad,
        )
