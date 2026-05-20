# AppIndemnizaciones

MVP en Python + Dash para calcular indemnización sustitutiva de vejez de trabajadores del sector público, usando:

- Archivo Excel/CSV de IPC histórico.
- PDF CETIL para periodos certificados y factores salariales.
- Motor de cálculo trazable y exportación a Excel.

## Estado del MVP

Este paquete inicial deja lista la arquitectura base, el extractor de IPC y el servicio de liquidación. El extractor CETIL queda como interfaz inicial para implementar lectura tabular avanzada con PyMuPDF/Camelot/Tabula según calidad del PDF.

## Arranque rápido

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Abrir:

```text
http://127.0.0.1:8050
```

## Flujo esperado

1. Cargar archivo IPC del Banco de la República/DANE.
2. Validar IPC actual detectado automáticamente o seleccionar fecha de liquidación.
3. Cargar PDF CETIL.
4. Revisar/corregir periodos y salarios antes de calcular.
5. Calcular liquidación.
6. Exportar Excel con trazabilidad.
