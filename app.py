from __future__ import annotations

import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app_indemnizaciones.ui.callbacks import register_callbacks  # noqa: E402
from app_indemnizaciones.ui.layout import build_layout  # noqa: E402


def create_app() -> dash.Dash:
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
        suppress_callback_exceptions=True,
    )
    app.title = "AppIndemnizaciones"
    app.layout = build_layout()
    register_callbacks(app)
    return app


app = create_app()
server = app.server


if __name__ == "__main__":
    app.run(debug=True)
