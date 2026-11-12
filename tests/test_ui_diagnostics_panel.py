from __future__ import annotations

from dash import html

from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    ExtractionIssue,
    ExtractionIssueCode,
    IssueSeverity,
)
from app_indemnizaciones.ui.diagnostics import build_cetil_diagnostics


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, str):
        yield from _walk(children)


def _details(panel):
    return [n for n in _walk(panel) if isinstance(n, html.Details)]


def _issue(severity: IssueSeverity) -> ExtractionIssue:
    code = next(iter(ExtractionIssueCode))
    return ExtractionIssue(
        code=code,
        severity=severity,
        message="mensaje",
        field="campo",
        page=1,
        action="haga algo",
        cause="causa larga",
    )


def test_solo_info_no_muestra_lista_abierta_y_campos_van_en_details():
    result = CetilExtractionResult(issues=[_issue(IssueSeverity.INFO)])
    panel = build_cetil_diagnostics(result)

    titles = [n.children for n in _walk(panel) if getattr(n, "className", "") == "diagnostics__section-title"]
    assert not any("atención" in str(t) for t in titles)
    details = _details(panel)
    summaries = [d.children[0].children for d in details if isinstance(d.children[0], html.Summary)]
    assert any("notas informativas" in s for s in summaries)
    assert any(s.startswith("Ver campos detectados") for s in summaries)
    assert all(not getattr(d, "open", False) for d in details)


def test_incidencia_warning_se_muestra_fuera_de_details():
    result = CetilExtractionResult(issues=[_issue(IssueSeverity.WARNING)])
    panel = build_cetil_diagnostics(result)

    titles = [str(n.children) for n in _walk(panel) if getattr(n, "className", "") == "diagnostics__section-title"]
    assert any("Requiere atención (1)" in t for t in titles)
