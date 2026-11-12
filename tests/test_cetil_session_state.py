from __future__ import annotations

from app_indemnizaciones.ui.layout import build_layout
from app_indemnizaciones.ui.state import clear_cetil_session_state, reset_state_for_new_cetil


def test_clear_cetil_state_preserves_ipc():
    ipc_state = [{"periodo": "2026-02", "indice": "155.73"}]

    state = clear_cetil_session_state(ipc_state=ipc_state)

    assert state["ipc_store"] == ipc_state
    assert state["cetil_store"] is None
    assert state["cetil_docs_store"] == []
    assert state["periodos_store"] == []
    assert state["resultado_store"] is None


def test_new_cetil_resets_periodos():
    cetil_state = {"metadata": {"numero_cetil": "B"}}

    state = reset_state_for_new_cetil(cetil_state, ipc_state=[{"periodo": "2026-02"}])

    assert state["cetil_store"] == cetil_state
    assert state["periodos_store"] == []


def test_new_cetil_resets_resultado():
    cetil_state = {"metadata": {"numero_cetil": "B"}}

    state = reset_state_for_new_cetil(cetil_state)

    assert state["resultado_store"] is None


def test_clear_cetil_button_empty_states():
    state = clear_cetil_session_state()

    assert state["cetil_store"] is None
    assert state["cetil_docs_store"] == []
    assert state["periodos_store"] == []
    assert state["resultado_store"] is None


def test_layout_has_multi_cetil_store_and_list():
    layout = build_layout()

    assert _find_component(layout, "cetil-docs-store") is not None
    assert _find_component(layout, "cetil-docs-list") is not None


def test_upload_cetil_acepta_varios_archivos():
    upload = _find_component(build_layout(), "upload-cetil")

    assert upload is not None
    assert upload.multiple is True


def test_layout_has_clear_cetil_button():
    assert _find_component_id(build_layout(), "btn-limpiar-cetil")


def test_layout_has_fecha_liquidacion_picker():
    assert _find_component_id(build_layout(), "fecha-liquidacion")


def _find_component_id(component: object, component_id: str) -> bool:
    return _find_component(component, component_id) is not None


def _find_component(component: object, component_id: str) -> object | None:
    if getattr(component, "id", None) == component_id:
        return component

    children = getattr(component, "children", None)
    if children is None:
        return None
    if isinstance(children, list | tuple):
        for child in children:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    return _find_component(children, component_id)
