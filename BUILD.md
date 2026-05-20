# BUILD.md

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ejecutar app

```bash
python app.py
```

## Tests

```bash
pytest -q
```

## Lint

```bash
ruff check .
```

## Build mínimo validado

El build se considera aceptable cuando:

- La app arranca sin error.
- El archivo IPC se carga y normaliza.
- `ipc_actual` se detecta desde el último mes válido.
- El motor de cálculo produce totales trazables.
- Las pruebas unitarias de IPC y liquidación pasan.

## Extracción CETIL

La lectura inicial de certificados CETIL usa `pdfplumber` para texto extraíble
con fallback a PyMuPDF. No usa OCR y no calcula automáticamente; los periodos
extraídos siempre pasan por revisión manual en la tabla editable.
