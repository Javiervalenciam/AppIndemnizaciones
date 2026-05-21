from __future__ import annotations

from decimal import Decimal

from app_indemnizaciones.utils.money import parse_money


def test_parse_money_formatos_requeridos():
    assert parse_money("14,000") == Decimal("14000")
    assert parse_money("14.000") == Decimal("14000")
    assert parse_money("14,000.00") == Decimal("14000.00")
    assert parse_money("14.000,00") == Decimal("14000.00")
    assert parse_money("$14.000") == Decimal("14000")
    assert parse_money("0.00") == Decimal("0.00")
    assert parse_money("") is None
