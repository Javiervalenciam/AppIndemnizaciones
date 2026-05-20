"""
Componentes reutilizables de UI.

Estas funciones son puramente presentacionales: no contienen lógica de
negocio, fórmulas ni acceso a servicios. Reciben datos ya preparados y
devuelven nodos Dash. Si necesita formato monetario o numérico avanzado,
hágalo en `ui/tables.py` o en una capa de presentación dedicada, no aquí.
"""

from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc
from dash import dcc, html


def section_title(title: str, subtitle: str | None = None) -> html.Div:
    children: list[Any] = [html.H3(title, className="step-card__title")]
    if subtitle:
        children.append(html.P(subtitle, className="step-card__subtitle"))
    return html.Div(children)


def step_card(
    number: int | str,
    title: str,
    body: Any,
    *,
    subtitle: str | None = None,
    extra_class: str = "",
) -> html.Div:
    """Tarjeta de paso con badge numerado, título y cuerpo libre."""
    return html.Div(
        [
            html.Div(
                [
                    html.Span(str(number), className="step-card__badge"),
                    section_title(title, subtitle=subtitle),
                ],
                className="step-card__header",
            ),
            html.Div(body, className="step-card__body"),
        ],
        className=f"step-card {extra_class}".strip(),
    )


def upload_zone(component_id: str, *, hint: str) -> dcc.Upload:
    return dcc.Upload(
        id=component_id,
        children=html.Div(hint),
        multiple=False,
        className="upload-zone",
    )


def info_alert(text: str, *, color: str = "info") -> dbc.Alert:
    return dbc.Alert(text, color=color, className="mb-0")


def metric_card(label: str, value: str, *, accent: bool = False) -> html.Div:
    cls = "metric-card metric-card--accent" if accent else "metric-card"
    return html.Div(
        [
            html.Span(label, className="metric-card__label"),
            html.Span(value, className="metric-card__value"),
        ],
        className=cls,
    )


def empty_periodos_placeholder() -> html.Div:
    return html.Div(
        "Aún no hay periodos. Use el botón “Agregar periodo” para empezar.",
        className="periodo-empty",
    )
