# claude.md

## Contexto de proyecto

AppIndemnizaciones convierte un Excel manual de indemnización sustitutiva de vejez en una aplicación Dash. La app debe cargar IPC histórico, extraer información de CETIL, calcular con trazabilidad y exportar una liquidación en Excel.

## Stack

- Python
- Dash
- pandas
- openpyxl/xlsxwriter
- PyMuPDF para primera fase de lectura PDF
- pytest

## Reglas de cálculo actuales

Por cada periodo:

```text
No. Días = DAYS360(fecha_desde, fecha_hasta) preferente; calendario como alternativa configurable.
No. Semanas = No. Días / 7
IBC Actualizado = IBL Reportado * (IPC Actual / IPC Inicial)
IBC Semanal Actualizado = (IBC Actualizado * 12) / 52.14
```

Totales:

```text
DÍAS EN TOTAL = suma días
SC = días totales / 7
SBC = promedio aritmético simple de IBC Semanal Actualizado
PPC = 0.0227
ISV = SBC * SC * PPC
```

## Fuente IPC

El Excel IPC del Banco de la República puede venir así:

- Hoja: `Datos`
- Fila 1: `Fecha`, `Índice de Precios al Consumidor (IPC)`
- Fila 2: formato/unidad, por ejemplo `yyyy/mm/dd`, `índice`
- Datos desde fila 3
- Al final puede traer notas como `Descargado de sistema...`; ignorarlas.

También se debe soportar formato alternativo:

- `Año(aaaa)-Mes(mm)`
- `Índice`

## Tareas sugeridas para Claude/Kiro

1. Completar UI de validación de CETIL.
2. Añadir parser tabular robusto para `PERIODOS CERTIFICADOS`.
3. Añadir parser de `FACTORES SALARIALES [AÑO]`.
4. Crear exportador Excel con plantilla visual oficial.
5. Agregar pruebas con fixtures anonimizados.
