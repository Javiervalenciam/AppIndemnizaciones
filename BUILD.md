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

## Inicio rapido en Windows

La forma recomendada para usuarios finales en Windows es:

1. Abrir la carpeta del proyecto.
2. Hacer doble clic en `iniciar_app.bat`.
3. Esperar a que se abra el navegador en `http://127.0.0.1:8050/`.
4. Para cerrar la app, volver a la consola y presionar `CTRL + C`.
5. Si ocurre un error, copiar el mensaje visible en la consola.

El archivo `iniciar_app.bat` crea `.venv` si no existe, activa el entorno,
instala dependencias y ejecuta `python app.py`.

Tambien existe `iniciar_app.ps1` como alternativa de PowerShell. Si Windows
bloquea la ejecucion de scripts, ejecutar una vez:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Para crear un acceso directo en el escritorio:

1. Clic derecho sobre `iniciar_app.bat`.
2. Seleccionar `Enviar a` > `Escritorio (crear acceso directo)`.
3. Opcional: renombrar el acceso directo como `AppIndemnizaciones`.

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
