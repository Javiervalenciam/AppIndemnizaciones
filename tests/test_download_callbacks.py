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
