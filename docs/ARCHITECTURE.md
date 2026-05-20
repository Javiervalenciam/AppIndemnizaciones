# Arquitectura inicial

## Capas

```text
app.py
└── ui/
    ├── layout.py
    └── callbacks.py
└── services/
    ├── ipc_loader.py
    ├── liquidacion_service.py
    ├── cetil_extractor.py
    └── excel_exporter.py
└── domain/
    ├── models.py
    └── exceptions.py
└── utils/
    ├── dates.py
    └── number_format.py
```

## Responsabilidades

### `app.py`

Inicializa Dash y registra layout/callbacks. No debe contener cálculos.

### `domain/`

Modelos puros de negocio: trabajador, periodo laborado, registros IPC, resultados por periodo y resultado total.

### `services/ipc_loader.py`

Carga Excel/CSV IPC, normaliza registros a periodo `YYYY-MM`, ignora filas basura y permite obtener IPC inicial/actual.

### `services/liquidacion_service.py`

Aplica fórmulas de indemnización sustitutiva sin depender de Dash.

### `services/cetil_extractor.py`

Extrae texto/bloques iniciales de CETIL. Todo lo extraído debe pasar a revisión manual.

### `services/excel_exporter.py`

Genera archivo Excel de salida con liquidación detallada.

## Decisión de diseño

Dash solo orquesta entrada/salida. La lógica legal, matemática y de extracción vive fuera de Dash para facilitar pruebas y migración futura.
