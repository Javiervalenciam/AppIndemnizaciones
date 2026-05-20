from __future__ import annotations

from datetime import date, datetime


def parse_date(value: object) -> date:
    """Parse common date values used in Excel/CETIL."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value is None:
        raise ValueError("Fecha vacía")

    text = str(value).strip()
    if not text:
        raise ValueError("Fecha vacía")

    formats = [
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y%m%d",
        "%Y%m",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%Y%m":
                return date(parsed.year, parsed.month, 1)
            return parsed.date()
        except ValueError:
            continue

    raise ValueError(f"Formato de fecha no soportado: {value!r}")


def to_period_yyyy_mm(value: object) -> str:
    parsed = parse_date(value)
    return f"{parsed.year:04d}-{parsed.month:02d}"


def commercial_360_days(start: date, end: date) -> int:
    """
    Equivalent to Excel DAYS360 US/NASD style for MVP purposes.

    It does not add one day. This matches the common Excel DAYS360(start, end)
    behavior used in the base workbook.
    """
    d1 = min(start.day, 30)
    d2 = end.day
    if d1 == 30 and d2 == 31:
        d2 = 30
    return (end.year - start.year) * 360 + (end.month - start.month) * 30 + (d2 - d1)


def calendar_days(start: date, end: date) -> int:
    return (end - start).days
