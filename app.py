from __future__ import annotations

import dash
import dash_bootstrap_components as dbc

from app_indemnizaciones.ui.callbacks import register_callbacks
from app_indemnizaciones.ui.layout import build_layout


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
