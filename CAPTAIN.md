# CAPTAIN.md

## Objetivo operativo

Dirigir el desarrollo incremental del MVP evitando dispersión técnica.

## Orden recomendado de implementación

1. IPC loader estable.
2. Motor matemático con pruebas.
3. UI Dash para carga IPC + periodos manuales.
4. Extractor CETIL básico.
5. Pantalla de revisión/corrección CETIL.
6. Exportación Excel.
7. Endurecimiento: validaciones, logs, errores, empaquetado.

## Decisiones congeladas para MVP

- Framework UI: Dash.
- Lenguaje: Python 3.11+.
- IPC actual: último registro válido del archivo, salvo que usuario elija fecha de liquidación.
- Cálculo base de días: comercial 360, configurable.
- No habrá base de datos en el MVP salvo que se requiera historial multiusuario.

## Criterio de avance

No pasar al extractor CETIL avanzado hasta que IPC loader y motor de cálculo tengan pruebas unitarias confiables.
