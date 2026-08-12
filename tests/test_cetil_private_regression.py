from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app_indemnizaciones.services.cetil_models import (
    CetilExtractionResult,
    CetilFactorSalarial,
    CetilMetadata,
    CetilPeriodoCertificado,
    CetilTrabajador,
    PeriodoLiquidableAnual,
)
from tests.private_cetil_support import (
    apply_exact_replacements,
    canonical_cetil_result,
    load_json,
    private_snapshot,
)

PRIVATE_DIR = Path(__file__).parent / "fixtures_private"
PRIVATE_PDFS: list[Path | None] = sorted(PRIVATE_DIR.glob("*.pdf")) or [None]
PRIVATE_IDS = [f"private_case_{index:03d}" for index in range(1, len(PRIVATE_PDFS) + 1)]


@pytest.mark.parametrize("pdf_path", PRIVATE_PDFS, ids=PRIVATE_IDS)
def test_private_cetil_matches_anonymizable_expected_json(pdf_path: Path | None) -> None:
    if pdf_path is None:
        pytest.skip("No private CETIL fixtures installed; see docs/CETILIA_REGRESSION_BASELINE.md")

    expected_path = pdf_path.with_suffix(".expected.json")
    redactions_path = pdf_path.with_suffix(".redactions.json")
    assert expected_path.exists(), "Missing private expected JSON; run the private snapshot generator."
    assert redactions_path.exists(), "Missing private redactions JSON; run the snapshot generator."

    replacements = load_json(redactions_path).get("replacements", {})
    actual = private_snapshot(pdf_path, replacements)
    expected = load_json(expected_path)

    assert actual == expected
    assert "texto_paginas" not in actual["result"]
    assert not _contains_key(actual["result"], "raw_text")


def test_private_snapshot_contract_excludes_full_text_and_supports_redaction() -> None:
    result = CetilExtractionResult(
        metadata=CetilMetadata(numero_cetil="PRIVATE-001"),
        trabajador=CetilTrabajador(documento="123", nombre_completo="Persona Privada"),
        periodos_certificados=[
            CetilPeriodoCertificado(
                fecha_desde=date(1983, 1, 1),
                fecha_hasta=date(1983, 12, 31),
                raw_text="FULL PRIVATE ROW TEXT",
            )
        ],
        factores_salariales=[
            CetilFactorSalarial(
                anio=1983,
                concepto="ASIGNACIÓN BÁSICA MENSUAL",
                valores_encontrados=[Decimal("1000")],
                raw_text="FULL PRIVATE SALARY TEXT",
            )
        ],
        filas_liquidables_anuales=[
            PeriodoLiquidableAnual(
                anio=1983,
                fecha_inicio=date(1983, 1, 1),
                fecha_fin=date(1983, 12, 31),
                ibl_reportado=Decimal("1000"),
            )
        ],
        texto_paginas={1: "FULL PRIVATE CERTIFICATE TEXT"},
        advertencias=["Advertencia sintética"],
        confidence_score=0.85,
    )

    canonical = canonical_cetil_result(result)
    redacted = apply_exact_replacements(
        canonical,
        {
            "PRIVATE-001": "<NUMERO_CETIL>",
            "123": "<DOCUMENTO>",
            "Persona Privada": "<NOMBRE_COMPLETO>",
        },
    )

    assert "texto_paginas" not in canonical
    assert not _contains_key(canonical, "raw_text")
    assert redacted["metadata"]["numero_cetil"] == "<NUMERO_CETIL>"
    assert redacted["trabajador"]["documento"] == "<DOCUMENTO>"
    assert redacted["trabajador"]["nombre_completo"] == "<NOMBRE_COMPLETO>"
    assert set(redacted) == {
        "metadata",
        "trabajador",
        "entidad_empleadora",
        "entidad_certificadora",
        "periodos_certificados",
        "factores_salariales",
        "filas_liquidables_anuales",
        "advertencias",
        "confidence_score",
    }


def _contains_key(value, target: str) -> bool:  # noqa: ANN001
    if isinstance(value, dict):
        return target in value or any(_contains_key(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False
