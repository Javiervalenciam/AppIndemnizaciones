# Importación IPC

## Archivo Banco de la República detectado

Estructura observada:

```text
Hoja: Datos
A1: Fecha
B1: Índice de Precios al Consumidor (IPC)
A2: yyyy/mm/dd
B2: índice
A3:B... datos mensuales
```

Ejemplo:

```text
1954/07/31 | 0.03
...
2026/02/28 | 155.73
2026/03/31 | 156.94
2026/04/30 | 158.17
```

Al final puede traer filas vacías o de trazabilidad de descarga. El extractor debe ignorarlas.

## Normalización

Cada fila válida se convierte a:

```python
IpcRegistro(
    periodo="YYYY-MM",
    fecha=date(...),
    indice=Decimal(...),
)
```

## IPC actual

Estrategia MVP:

1. Si el usuario selecciona fecha de liquidación, usar el IPC del mes/año seleccionado.
2. Si no selecciona fecha, usar el último registro válido del archivo IPC cargado.

## Errores esperados

- Archivo vacío.
- Formato no soportado.
- Sin columna de fecha/periodo.
- Sin columna de índice IPC.
- Mes solicitado inexistente en el archivo.

## Formatos soportados

### Banco República

```text
Fecha | Índice de Precios al Consumidor (IPC)
```

### Histórico alternativo

```text
Año(aaaa)-Mes(mm) | Índice
```
