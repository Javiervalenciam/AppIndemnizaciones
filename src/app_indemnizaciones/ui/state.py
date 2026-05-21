from __future__ import annotations

from typing import Any

EMPTY_CETIL_STATE = None
EMPTY_PERIODOS_STATE: list[dict[str, str]] = []
EMPTY_RESULTADO_STATE = None


def clear_cetil_session_state(ipc_state: Any = None) -> dict[str, Any]:
    return {
        "ipc_store": ipc_state,
        "cetil_store": EMPTY_CETIL_STATE,
        "periodos_store": list(EMPTY_PERIODOS_STATE),
        "resultado_store": EMPTY_RESULTADO_STATE,
    }


def reset_state_for_new_cetil(cetil_state: Any, ipc_state: Any = None) -> dict[str, Any]:
    state = clear_cetil_session_state(ipc_state=ipc_state)
    state["cetil_store"] = cetil_state
    return state
