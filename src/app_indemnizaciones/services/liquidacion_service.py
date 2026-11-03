from __future__ import annotations

from datetime import date
from decimal import Decimal, getcontext

from app_indemnizaciones.config import MONTHLY_TO_WEEKLY_DIVISOR, CalculationConfig
from app_indemnizaciones.domain.exceptions import IpcNotFoundError, LiquidacionError
from app_indemnizaciones.domain.models import (
    IpcRegistro,
    PeriodoLaborado,
    ResultadoLiquidacion,
    ResultadoPeriodo,
)
from app_indemnizaciones.services.ipc_loader import IpcRepository
from app_indemnizaciones.utils.dates import calendar_days, commercial_360_days, parse_date

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
        fecha_normalizada, warnings = self._normalize_fecha_liquidacion(fecha_liquidacion)
        ipc_actual, ipc_fuente = self._resolve_ipc_actual(fecha_normalizada, warnings)

        resultados = [
            self._calcular_periodo(
                periodo,
                ipc_actual=ipc_actual,
                day_count=convention,
            )
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
            fecha_liquidacion=fecha_normalizada,
            ipc_actual_periodo=ipc_actual.periodo,
            ipc_actual_fuente=ipc_fuente,
            advertencias=tuple(warnings),
        )

    def _normalize_fecha_liquidacion(
        self, fecha_liquidacion: object | None
    ) -> tuple[date | None, list[str]]:
        if fecha_liquidacion is None or str(fecha_liquidacion).strip() == "":
            return None, []
        try:
            return parse_date(fecha_liquidacion), []
        except ValueError as exc:
            raise LiquidacionError(
                f"Fecha de liquidación inválida: {fecha_liquidacion!r}. Use el formato AAAA-MM-DD."
            ) from exc

    def _resolve_ipc_actual(
        self,
        fecha_liquidacion: date | None,
        warnings: list[str],
    ) -> tuple[IpcRegistro, str]:
        if fecha_liquidacion is None:
            current = self.ipc_repository.get_current_ipc()
            warnings.append(
                "No se indicó fecha de liquidación: se usó el IPC más reciente disponible "
                f"({current.periodo}). Para una liquidación reproducible indique la fecha."
            )
            return current, "ultimo_registro"

        try:
            current = self.ipc_repository.obtener_por_fecha(fecha_liquidacion)
        except IpcNotFoundError as exc:
            summary = self.ipc_repository.summary()
            raise LiquidacionError(
                "No existe IPC para el periodo de la fecha de liquidación "
                f"{fecha_liquidacion.isoformat()}. El archivo IPC cargado cubre "
                f"{summary.periodo_minimo} a {summary.periodo_maximo}. "
                "Cargue un IPC actualizado o elija una fecha dentro del rango."
            ) from exc
        return current, "fecha_liquidacion"

    def _calcular_periodo(
        self,
        periodo: PeriodoLaborado,
        ipc_actual: IpcRegistro,
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
