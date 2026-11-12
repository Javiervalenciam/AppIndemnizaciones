"""Genera assets/favicon.ico y assets/icon/app_icon.png desde app_icon.svg.

Uso: python scripts/build_icon.py (con el venv activo)
Usa PyMuPDF (ya es dependencia del proyecto) para rasterizar el SVG y Pillow para
empaquetar el .ico multi-resolución.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "icon" / "app_icon.svg"
SIZES = (256, 128, 64, 48, 32, 24, 16)


def render(size: int) -> Image.Image:
    doc = fitz.open(str(SVG))
    page = doc[0]
    zoom = size / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
    return Image.open(BytesIO(pix.tobytes("png"))).convert("RGBA")


def main() -> None:
    master = render(512)
    master.save(ROOT / "assets" / "icon" / "app_icon.png")
    ico = ROOT / "assets" / "favicon.ico"
    master.save(ico, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"OK: {ico} ({', '.join(str(s) for s in SIZES)} px)")


if __name__ == "__main__":
    main()
