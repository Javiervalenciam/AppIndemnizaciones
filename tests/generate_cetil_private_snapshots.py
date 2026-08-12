from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from tests.private_cetil_support import (
    canonical_cetil_result,
    load_json,
    private_snapshot,
    suggested_replacements,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_DIR = Path(__file__).parent / "fixtures_private"
PRIVATE_IGNORE_RULE = "tests/fixtures_private/"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare ignored CETIL PDFs and anonymizable regression snapshots."
    )
    parser.add_argument("--source-dir", type=Path, help="External directory containing private PDFs.")
    parser.add_argument("--private-dir", type=Path, default=DEFAULT_PRIVATE_DIR)
    parser.add_argument("--force", action="store_true", help="Replace local PDFs and snapshots.")
    args = parser.parse_args()

    _require_private_ignore_rule()
    private_dir = args.private_dir.resolve()
    private_dir.mkdir(parents=True, exist_ok=True)

    if args.source_dir:
        source_pdfs = sorted(args.source_dir.resolve().glob("*.pdf"))
        for index, source in enumerate(source_pdfs, start=1):
            destination = private_dir / f"case_{index:03d}.pdf"
            if args.force or not destination.exists():
                shutil.copyfile(source, destination)

    private_pdfs = sorted(private_dir.glob("*.pdf"))
    if not private_pdfs:
        print("No private CETIL PDFs found; infrastructure is ready.")
        return 0

    for index, pdf_path in enumerate(private_pdfs, start=1):
        case_label = f"private_case_{index:03d}"
        redactions_path = pdf_path.with_suffix(".redactions.json")
        expected_path = pdf_path.with_suffix(".expected.json")

        result = CetilExtractor().extract(pdf_path)
        canonical = canonical_cetil_result(result)
        if redactions_path.exists():
            replacements = load_json(redactions_path).get("replacements", {})
        else:
            replacements = suggested_replacements(canonical)
            _write_json(redactions_path, {"replacements": replacements})

        if args.force or not expected_path.exists():
            _write_json(expected_path, private_snapshot(pdf_path, replacements))
            state = "snapshot_created"
        else:
            state = "snapshot_preserved"
        print(f"{case_label}: {state}; full_text_excluded=true")

    return 0


def _require_private_ignore_rule() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    if PRIVATE_IGNORE_RULE not in gitignore:
        raise RuntimeError(f"Missing required .gitignore rule: {PRIVATE_IGNORE_RULE}")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
