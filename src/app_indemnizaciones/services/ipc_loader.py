from __future__ import annotations

import base64
import io
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from app_indemnizaciones.domain.exceptions import IpcImportError, IpcNotFoundError
from app_indemnizaciones.domain.models import IpcPair, IpcRegistro
from app_indemnizaciones.utils.dates import parse_date, to_period_yyyy_mm
from app_indemnizaciones.utils.number_format import parse_decimal


@dataclass(frozen=True)
class IpcImportSummary:
    total_registros: int
    periodo_minimo: str
    periodo_maximo: str
    ipc_actual: Decimal


@dataclass(frozen=True)
class IpcAnnualAverageInfo:
    year: int
    average: Decimal
    months_count: int
    missing_months: list[int]
    warnings: list[str]


def _clean_column_name(value: object) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    return " ".join(text.replace("_", " ").split())


def _first_matching_column(columns: list[object], candidates: tuple[str, ...]) -> object | None:
    normalized = {col: _clean_column_name(col) for col in columns}
    for col, clean in normalized.items():
        if any(candidate in clean for candidate in candidates):
            return col
    return None


class IpcRepository:
    """
    Loads and queries historical IPC.

    Supported schemas:
    1. Banco República style:
       - Fecha
       - Índice de Precios al Consumidor (IPC)

    2. DANE/legacy style:
       - Año(aaaa)-Mes(mm), e.g. 198309
       - Índice
    """

    def __init__(self, registros: list[IpcRegistro]) -> None:
        if not registros:
            raise IpcImportError("El archivo IPC no contiene registros válidos.")

        ordered = sorted(registros, key=lambda row: row.periodo)
        self._registros = ordered
        self._by_period = {row.periodo: row for row in ordered}

    @classmethod
    def from_path(cls, path: str | Path, sheet_name: str | None = "Datos") -> IpcRepository:
        path = Path(path)
        if not path.exists():
            raise IpcImportError(f"No existe el archivo IPC: {path}")

        suffix = path.suffix.lower()
        try:
            if suffix in {".xlsx", ".xlsm", ".xls"}:
                df = cls._read_excel(path, sheet_name=sheet_name)
            elif suffix == ".csv":
                df = pd.read_csv(path)
            else:
                raise IpcImportError(f"Formato IPC no soportado: {suffix}")
        except IpcImportError:
            raise
        except Exception as exc:
            raise IpcImportError(f"No fue posible leer el archivo IPC: {exc}") from exc

        return cls.from_dataframe(df)

    @classmethod
    def from_upload_contents(cls, contents: str, filename: str) -> IpcRepository:
        """Build repository from Dash Upload `contents` string."""
        if not contents or "," not in contents:
            raise IpcImportError("Contenido de carga IPC inválido.")
        _, encoded = contents.split(",", 1)
        raw = base64.b64decode(encoded)
        suffix = Path(filename).suffix.lower()

        try:
            if suffix in {".xlsx", ".xlsm", ".xls"}:
                df = cls._read_excel(io.BytesIO(raw), sheet_name="Datos")
            elif suffix == ".csv":
                df = pd.read_csv(io.BytesIO(raw))
            else:
                raise IpcImportError(f"Formato IPC no soportado: {suffix}")
        except IpcImportError:
            raise
        except Exception as exc:
            raise IpcImportError(f"No fue posible procesar el archivo IPC cargado: {exc}") from exc

        return cls.from_dataframe(df)

    @staticmethod
    def _read_excel(path_or_buffer: str | Path | BinaryIO, sheet_name: str | None = "Datos") -> pd.DataFrame:
        xls = pd.ExcelFile(path_or_buffer)
        selected_sheet = sheet_name if sheet_name in xls.sheet_names else xls.sheet_names[0]
        return pd.read_excel(xls, sheet_name=selected_sheet, dtype=object)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> IpcRepository:
        if df.empty:
            raise IpcImportError("La tabla IPC está vacía.")

        columns = list(df.columns)
        fecha_col = _first_matching_column(columns, ("fecha",))
        periodo_col = _first_matching_column(columns, ("ano(aaaa)-mes(mm)", "año(aaaa)-mes(mm)", "aaaa", "mes"))
        indice_col = _first_matching_column(columns, ("indice de precios", "indice", "ipc"))

        if indice_col is None:
            raise IpcImportError(
                "No se encontró columna de índice IPC. Esperado: 'Índice' o "
                "'Índice de Precios al Consumidor (IPC)'."
            )

        registros: list[IpcRegistro] = []
        for _, row in df.iterrows():
            try:
                indice = parse_decimal(row[indice_col])
                if indice <= 0:
                    continue

                if fecha_col is not None:
                    fecha = parse_date(row[fecha_col])
                    periodo = f"{fecha.year:04d}-{fecha.month:02d}"
                elif periodo_col is not None:
                    raw_period = str(row[periodo_col]).strip().replace(".0", "")
                    if len(raw_period) != 6 or not raw_period.isdigit():
                        continue
                    year = int(raw_period[:4])
                    month = int(raw_period[4:6])
                    fecha = date(year, month, 1)
                    periodo = f"{year:04d}-{month:02d}"
                else:
                    raise IpcImportError(
                        "No se encontró columna de fecha o periodo. Esperado: 'Fecha' o "
                        "'Año(aaaa)-Mes(mm)'."
                    )

                registros.append(IpcRegistro(periodo=periodo, fecha=fecha, indice=indice))
            except (ValueError, TypeError, KeyError):
                # Ignora filas de unidades, notas de descarga, filas vacías o textos no tabulares.
                continue

        # Deduplicar por periodo: conservar último registro válido del mes.
        unique: dict[str, IpcRegistro] = {row.periodo: row for row in registros}
        if not unique:
            raise IpcImportError("No se pudo normalizar ningún registro IPC válido.")
        return cls(list(unique.values()))

    @property
    def registros(self) -> list[IpcRegistro]:
        return list(self._registros)

    def summary(self) -> IpcImportSummary:
        first = self._registros[0]
        latest = self._registros[-1]
        return IpcImportSummary(
            total_registros=len(self._registros),
            periodo_minimo=first.periodo,
            periodo_maximo=latest.periodo,
            ipc_actual=latest.indice,
        )

    def ultimo_registro(self) -> IpcRegistro:
        return self._registros[-1]

    def get_current_ipc(self) -> IpcRegistro:
        return self.ultimo_registro()

    def get_annual_average_ipc_info(self, year: int) -> IpcAnnualAverageInfo:
        year_records = [row for row in self._registros if row.fecha.year == year and row.indice > 0]
        if not year_records:
            raise IpcNotFoundError(f"No existe IPC válido para el año {year}.")

        by_month = {row.fecha.month: row for row in year_records}
        months = sorted(by_month)
        average = sum((by_month[month].indice for month in months), Decimal(0)) / Decimal(len(months))
        missing_months = [month for month in range(1, 13) if month not in by_month]
        warnings = []
        if len(months) < 12:
            warnings.append(
                f"El año {year} tiene {len(months)} registros IPC; "
                "se usó promedio con meses disponibles."
            )

        return IpcAnnualAverageInfo(
            year=year,
            average=average,
            months_count=len(months),
            missing_months=missing_months,
            warnings=warnings,
        )

    def get_annual_average_ipc(self, year: int) -> Decimal:
        return self.get_annual_average_ipc_info(year).average

    def obtener_por_fecha(self, fecha: object) -> IpcRegistro:
        periodo = to_period_yyyy_mm(fecha)
        try:
            return self._by_period[periodo]
        except KeyError as exc:
            raise IpcNotFoundError(f"No existe IPC para el periodo {periodo}.") from exc

    def obtener_ipc(self, fecha_historica: object, fecha_actual: object | None = None) -> IpcPair:
        inicial = self.obtener_por_fecha(fecha_historica)
        actual = self.obtener_por_fecha(fecha_actual) if fecha_actual else self.ultimo_registro()
        return IpcPair(
            periodo_inicial=inicial.periodo,
            ipc_inicial=inicial.indice,
            periodo_actual=actual.periodo,
            ipc_actual=actual.indice,
        )
