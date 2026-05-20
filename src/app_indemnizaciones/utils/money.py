from __future__ import annotations

from decimal import Decimal

from app_indemnizaciones.services.period_normalizer import parse_ibl_decimal


def parse_money(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return parse_ibl_decimal(text)
