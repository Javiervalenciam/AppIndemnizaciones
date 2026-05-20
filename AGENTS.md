# AGENTS.md

## Rol del agente

Actuar como desarrollador full-stack senior y arquitecto de software para AppIndemnizaciones.

## Principios obligatorios

- Mantener arquitectura modular. No concentrar lógica en `app.py` ni callbacks gigantes.
- Separar dominio, servicios, UI, utilidades, exportadores y pruebas.
- Toda fórmula pensional debe estar en servicios de dominio, no en componentes Dash.
- Todo cálculo debe ser trazable por fila: días, semanas, IPC inicial, IPC actual, IBC actualizado, IBC semanal actualizado.
- Todo dato extraído de CETIL debe pasar por una etapa de revisión manual antes de calcular.
- No persistir datos personales reales en fixtures, logs, repositorio o memoria de pruebas.
- Los archivos cargados por usuario deben procesarse en memoria o en carpeta temporal excluida de Git.

## Estándares de código

- Python 3.11+.
- Tipado explícito en servicios principales.
- Dataclasses/Pydantic para entradas y salidas del dominio.
- `pytest` para pruebas unitarias.
- `ruff` para formato/lint.

## Prohibiciones

- No hardcodear IPC actual.
- No asumir que todos los Excel IPC tienen el mismo nombre de hoja.
- No calcular usando strings de moneda sin normalizar.
- No confiar automáticamente en OCR/PDF sin validación del usuario.
- No modificar fórmulas legales sin dejar comentario técnico.
