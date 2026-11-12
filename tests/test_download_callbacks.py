from __future__ import annotations

from app import create_app


def test_callback_calculo_no_dispara_descarga():
    app = create_app()
    callback = _callback_by_input(app.callback_map, "btn-calcular")

    output_ids = _output_ids(callback["output"])

    assert "download-liquidacion" not in output_ids
    assert output_ids == {"resultado-liquidacion", "resultado-store"}


def test_callback_descarga_usa_resultado_store():
    app = create_app()
    callback = _callback_by_input(app.callback_map, "btn-download")

    state_ids = {state["id"] for state in callback["state"]}

    assert callback["output"].component_id == "download-liquidacion"
    assert "resultado-store" in state_ids
    assert "cetil-store" in state_ids


def _callback_by_input(callback_map: dict, input_id: str) -> dict:
    for callback in callback_map.values():
        if any(item["id"] == input_id for item in callback["inputs"]):
            return callback
    raise AssertionError(f"No callback found for input {input_id}")


def _output_ids(output: object) -> set[str]:
    if isinstance(output, list):
        return {item.component_id for item in output}
    return {output.component_id}


def test_descarga_no_se_dispara_al_crear_el_boton():
    from dash import no_update

    app = create_app()
    callback = _callback_by_input(app.callback_map, "btn-download")
    func = callback["callback"].__wrapped__ if hasattr(callback["callback"], "__wrapped__") else callback["callback"]

    # n_clicks=None simula la inserción dinámica del botón tras calcular.
    assert func(None, {"periodos": []}, None, None) is no_update


def test_layout_fecha_liquidacion_por_defecto_es_hoy():
    from datetime import date

    from app_indemnizaciones.ui.layout import build_layout

    def find(node, target):
        if getattr(node, "id", None) == target:
            return node
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                found = find(child, target)
                if found is not None:
                    return found
        elif children is not None and not isinstance(children, str):
            return find(children, target)
        return None

    picker = find(build_layout(), "fecha-liquidacion")
    assert picker is not None
    assert picker.date == date.today().isoformat()


def _callback_func(app, output_id: str):
    for cb in app.callback_map.values():
        out = cb["output"]
        ids = {o.component_id for o in out} if isinstance(out, list) else {out.component_id}
        if output_id in ids or f"{output_id}.value" in str(cb.get("output", "")):
            fn = cb["callback"]
            return getattr(fn, "__wrapped__", fn)
    raise AssertionError(output_id)


def test_genero_manual_actualiza_cetil_store_sin_ciclo():
    from dash import no_update

    app = create_app()
    func = _callback_func(app, "genero-manual")  # sync (value) callback
    store = {"trabajador": {"genero": None, "genero_origen": None}}

    setter = None
    for cb in app.callback_map.values():
        if any(i["id"] == "genero-manual" for i in cb["inputs"]):
            setter = getattr(cb["callback"], "__wrapped__", cb["callback"])
    assert setter is not None

    nuevo = setter("Mujer", store)
    assert nuevo["trabajador"]["genero"] == "Mujer"
    assert nuevo["trabajador"]["genero_origen"] == "manual"
    # Mismo valor que ya está en el store: no debe re-emitir (rompe el ciclo).
    assert setter("Mujer", nuevo) is no_update
    assert func is not None
