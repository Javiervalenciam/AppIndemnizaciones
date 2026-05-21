from app_indemnizaciones.ui.callbacks import _build_ipc_kpi


def test_ipc_status_renderiza_kpi_no_alerta_textual():
    component = _build_ipc_kpi(
        {
            "filename": "ipc_test.csv",
            "total_registros": 862,
            "periodo_minimo": "1954-07",
            "periodo_maximo": "2026-04",
            "ipc_actual": "158.17",
        }
    )

    assert component.className == "ipc-kpi"
    assert component.children[0].className == "ipc-kpi__header"
    assert component.children[1].className == "ipc-kpi__grid"
    assert component.children[1].children[0].children[1].children == "2026-04"
    assert component.children[1].children[1].children[1].children == "158.17"
