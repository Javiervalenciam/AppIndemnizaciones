from __future__ import annotations

from app_indemnizaciones.services.cetil_models import (
    CetilTrabajador,
    _trabajador_from_dict,
    _trabajador_to_dict,
)
from app_indemnizaciones.services.gender_resolver import (
    DEFAULT_CSV_PATH,
    GeneroResolucion,
    resolve_genero,
)


def _csv(tmp_path):
    path = tmp_path / "nombres.csv"
    path.write_bytes(
        "﻿nombre,genero\r\nJosé,Hombre\r\nMaría,Mujer\r\nAndrea,Mujer\r\n"
        "Ariel,Hombre\r\nAriel,Mujer\r\nSantiago,Hombre\r\n".encode("utf-8")
    )
    return path


def test_resolucion_simple_con_bom_y_crlf(tmp_path):
    res = resolve_genero("Andrea Perez Gomez", csv_path=_csv(tmp_path))
    assert res == GeneroResolucion(valor="Mujer", origen="base_nombres", nombre_usado="andrea")


def test_tildes_mayusculas_y_espacios(tmp_path):
    p = _csv(tmp_path)
    assert resolve_genero("  JOSE   PEREZ ", csv_path=p).valor == "Hombre"
    assert resolve_genero("maría", csv_path=p).valor == "Mujer"


def test_ambiguo_devuelve_none(tmp_path):
    assert resolve_genero("Ariel Lopez", csv_path=_csv(tmp_path)) is None


def test_desconocido_y_vacio_devuelven_none(tmp_path):
    p = _csv(tmp_path)
    assert resolve_genero("Zzyzx Lopez", csv_path=p) is None
    assert resolve_genero(None, csv_path=p) is None
    assert resolve_genero("   ", csv_path=p) is None


def test_nombre_compuesto_decide_el_primer_nombre(tmp_path):
    p = _csv(tmp_path)
    assert resolve_genero("María José Rojas", csv_path=p).valor == "Mujer"
    assert resolve_genero("José María Rojas", csv_path=p).valor == "Hombre"


def test_segundo_nombre_si_el_primero_es_desconocido_o_ambiguo(tmp_path):
    p = _csv(tmp_path)
    assert resolve_genero("Ariel Andrea Rojas", csv_path=p).valor == "Mujer"
    assert resolve_genero("Zzyzx Andrea Rojas", csv_path=p).valor == "Mujer"


def test_apellidos_no_se_usan(tmp_path):
    assert resolve_genero("Zzyzx Qwerty Santiago", csv_path=_csv(tmp_path)) is None


def test_csv_inexistente_devuelve_none(tmp_path):
    assert resolve_genero("Andrea", csv_path=tmp_path / "no_existe.csv") is None


def test_csv_real_versionado():
    assert DEFAULT_CSV_PATH.exists()
    assert resolve_genero("Maria Fernanda").valor == "Mujer"
    assert resolve_genero("JOSÉ Luis").valor == "Hombre"
    assert resolve_genero("Xxxxqqq") is None


def test_genero_origen_serializacion_retrocompatible():
    t = CetilTrabajador(documento="1", genero="Mujer", genero_origen="base_nombres")
    assert _trabajador_from_dict(_trabajador_to_dict(t)) == t
    legacy = _trabajador_to_dict(t)
    legacy.pop("genero_origen")
    assert _trabajador_from_dict(legacy).genero_origen is None
