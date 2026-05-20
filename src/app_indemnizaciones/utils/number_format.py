from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise ValueError("Valor numérico vacío")
    text = str(value).strip()
    if not text:
        raise ValueError("Valor numérico vacío")

    # Normaliza moneda/valores: "$ 1,234.56" -> "1234.56".
    text = text.replace("$", "").replace(" ", "").replace("\u00a0", "")

    # Caso latino: "1.234,56" -> "1234.56"
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")

    try:
        number = Decimal(text)
        if not number.is_finite():
            raise ValueError(f"Valor numérico no soportado: {value!r}")
        return number
    except InvalidOperation as exc:
        raise ValueError(f"Valor numérico no soportado: {value!r}") from exc
