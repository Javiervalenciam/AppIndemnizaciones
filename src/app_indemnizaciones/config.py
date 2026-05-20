from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalculationConfig:
    ppc: float = 0.0227
    weeks_per_year: float = 52.14
    months_per_year: int = 12
    default_day_count: str = "commercial_360"


@dataclass(frozen=True)
class AppConfig:
    app_title: str = "AppIndemnizaciones"
    calculation: CalculationConfig = CalculationConfig()
