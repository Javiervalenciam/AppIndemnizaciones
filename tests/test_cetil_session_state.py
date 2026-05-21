from __future__ import annotations

from app_indemnizaciones.ui.layout import build_layout
from app_indemnizaciones.ui.state import clear_cetil_session_state, reset_state_for_new_cetil


def test_clear_cetil_state_preserves_ipc():
    ipc_state = [{"periodo": "2026-02", "indice": "155.73"}]

    state = clear_cetil_session_state(ipc_state=ipc_state)

    assert state["ipc_store"] == ipc_state
    assert state["cetil_store"] is None
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
    assert state["periodos_store"] == []
    assert state["resultado_store"] is None


def test_layout_has_clear_cetil_button():
    assert _find_component_id(build_layout(), "btn-limpiar-cetil")


def _find_component_id(component: object, component_id: str) -> bool:
    if getattr(component, "id", None) == component_id:
        return True

    children = getattr(component, "children", None)
    if children is None:
        return False
    if isinstance(children, list | tuple):
        return any(_find_component_id(child, component_id) for child in children)
    return _find_component_id(children, component_id)
