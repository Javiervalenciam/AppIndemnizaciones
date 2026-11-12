"""Inferencia informativa del género a partir del nombre de pila.

El CETIL no trae el género. Este módulo consulta una base de nombres
(``src/app_indemnizaciones/data/nombre_genero.csv``, columnas ``nombre,genero``).
El género NO interviene en ningún cálculo; es solo informativo.

Reglas:
- ``nombre_completo`` llega en orden NOMBRES APELLIDOS (el extractor lo arma como
  primer_nombre, segundo_nombre, primer_apellido, segundo_apellido).
- Solo se consideran los dos primeros tokens (nombres de pila). Los apellidos nunca
  se usan, porque pueden coincidir con nombres (p. ej. "Santiago", "Martin").
- Decide el primer token que esté en la base (convención: "María José" => Mujer,
  "José María" => Hombre). El segundo token solo se usa si el primero no es
  conocido o es ambiguo en la base.
- Nombre duplicado con géneros distintos en la base => ambiguo => no resuelve.
- Sin coincidencia clara => ``None``. Nunca se adivina.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "nombre_genero.csv"
ORIGEN_BASE_NOMBRES = "base_nombres"
_VALID = {"hombre": "Hombre", "mujer": "Mujer"}
_GIVEN_NAME_TOKENS = 2
_AMBIGUOUS = "?"


@dataclass(frozen=True)
class GeneroResolucion:
    valor: str  # "Hombre" | "Mujer"
    origen: str  # "base_nombres"
    nombre_usado: str  # token de la base que decidió (en minúsculas normalizadas)


def normalize_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _load_table(path: Path) -> dict[str, str]:
    table: dict[str, str] = {}
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError:
        return table
    with handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            name = normalize_name(row[0])
            genero = _VALID.get(normalize_name(row[1]))
            if not name or genero is None:  # cabecera o fila inválida
                continue
            if table.get(name, genero) != genero:
                table[name] = _AMBIGUOUS
            else:
                table[name] = genero
    return table


@lru_cache(maxsize=4)
def _cached_table(path_str: str) -> dict[str, str]:
    return _load_table(Path(path_str))


def resolve_genero(
    nombre_completo: str | None,
    csv_path: str | Path | None = None,
) -> GeneroResolucion | None:
    """Devuelve el género inferido o ``None`` si no hay coincidencia clara."""
    normalized = normalize_name(nombre_completo)
    if not normalized:
        return None
    table = _cached_table(str(csv_path or DEFAULT_CSV_PATH))
    if not table:
        return None
    tokens = re.findall(r"[a-zñ]+", normalized)[:_GIVEN_NAME_TOKENS]
    for token in tokens:
        genero = table.get(token)
        if genero in _VALID.values():
            return GeneroResolucion(valor=genero, origen=ORIGEN_BASE_NOMBRES, nombre_usado=token)
    return None
