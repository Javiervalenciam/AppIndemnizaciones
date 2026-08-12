# Línea base de regresión AppIndemnizaciones → CETILIA

**Fecha:** 2026-08-12  
**Fase:** 2 - congelación y blindaje del comportamiento actual  
**Rama local:** `chore/cetilia-regression-baseline`  
**Commit de partida:** `579ce8af744d003839dd0ad99b3a28239fd56738`

Esta línea base caracteriza el comportamiento que AppIndemnizaciones tiene hoy. Una prueba verde
significa “el comportamiento no cambió”; no significa que la regla haya sido validada jurídica o
documentalmente. En esta fase no se modificaron fórmulas, motor, extractor, IPC, frontend ni módulos
productivos.

## Verificación previa del repositorio

La verificación se ejecutó antes de crear la rama o editar archivos:

| Elemento | Resultado observado |
|---|---|
| Rama inicial | `main` |
| Commit | `579ce8af744d003839dd0ad99b3a28239fd56738` |
| Origin local | `https://github.com/Davincce/AppIndemnizaciones.git` |
| Working tree | Limpio; `git status --porcelain=v1` no produjo entradas. |
| Pytest inicial | `76 passed, 5 warnings` |
| Ruff inicial | `All checks passed!` sobre `app.py src tests` |

La referencia entregada para el proyecto fue `Javiervalenciam/AppIndemnizaciones`, mientras que el
checkout local apunta a `Davincce/AppIndemnizaciones`. La discrepancia queda documentada; no se
cambió el remoto ni se intentó sincronizar otro repositorio.

Los cinco warnings iniciales son una sola deprecación de `dash_table.DataTable` reportada en la
carga de Dash y en cuatro pruebas que construyen componentes. No se corrigió en esta fase.

## A. Pruebas existentes

La suite original tenía 76 pruebas distribuidas así:

| Archivo | Comportamiento cubierto antes de esta fase |
|---|---|
| `test_cetil_extractor.py` | Metadatos, trabajador, entidad, periodos textuales, salarios y bloques multipágina sintéticos. |
| `test_cetil_session_state.py` | Limpieza/reinicio de stores CETIL y presencia del botón. |
| `test_download_callbacks.py` | Separación entre cálculo y descarga. |
| `test_excel_base_regression.py` | Anualización 1983-1988 y vector sintético del Excel base. |
| `test_excel_exporter.py` | Estructura, fórmulas, metadatos y nombre del XLSX. |
| `test_ipc_loader.py` | Dos esquemas IPC, promedio anual, faltantes y último registro. |
| `test_ipc_status_kpi.py` | Presentación del resumen IPC. |
| `test_liquidacion_service.py` | Cálculo por periodo, promedio IPC y ausencia de redondeo intermedio. |
| `test_money.py` | Formatos monetarios del extractor. |
| `test_period_normalizer.py` | Fila canónica, división anual, consolidación, brechas e IBL. |
| `test_period_validators.py` | Errores, advertencias, duplicados y solapamientos. |
| `test_serialization.py` | Ida/vuelta de filas UI. |
| `test_ui_tables.py` | Campos editables y ocultos. |

Limitación congelada: esas pruebas usaban texto y DataFrames sintéticos; no había PDFs, IPC reales o
libros Excel de referencia versionados.

## B. Nuevas pruebas

### B.1 Motor dorado

`tests/test_cetilia_liquidacion_regression.py` consume
`tests/fixtures/regression/liquidacion_service_baseline.json` y compara exactamente:

- entradas: fechas, año, IBL e histórico IPC;
- por fila: días, semanas, IPC inicial/final, IBC mensual y semanal;
- totales: días, SC, SBC, PPC e ISV.

Los ocho casos dorados son:

1. un periodo;
2. cuatro periodos, varios años y salarios diferentes;
3. periodo de un día;
4. cambio de año;
5. febrero de año no bisiesto;
6. febrero de año bisiesto;
7. borde 30/31 de mes;
8. dos periodos con brecha.

Todos los importes se reconstruyen con `Decimal` y se comparan sin `quantize()`.

### B.2 IPC y fecha de liquidación

`tests/test_cetilia_ipc_characterization.py` agrega 11 pruebas para formatos numéricos, vacíos,
duplicados, meses faltantes, año incompleto, último registro, futuro y el bug de fecha de
liquidación. Las pruebas defectuosas están rotuladas `CURRENT_BEHAVIOR` o
`KNOWN_BUG_FECHA_LIQUIDACION`.

### B.3 Anualización, duplicados y solapamientos

`tests/test_cetilia_period_characterization.py` agrega cinco pruebas:

- duplicado advertido pero calculado dos veces;
- solapamiento advertido pero sumado;
- contiguos CETIL consolidados;
- brecha que conserva varias filas del mismo año;
- pérdida legada de fechas al anualizar el cruce 1987-1988.

### B.4 Excel

`tests/test_cetilia_excel_regression.py` agrega dos pruebas. La primera contrasta cada fila y total de
`ResultadoLiquidacion` con los valores cacheados del XLSX. La segunda congela las fórmulas duplicadas
que Excel escribe para días, semanas, indexación, IBC semanal, SC, PPC, SBC e ISV.

### B.5 CETIL privado

- `tests/private_cetil_support.py`: contrato canónico, exclusión de texto completo, seudonimización y
  hash del PDF.
- `tests/generate_cetil_private_snapshots.py`: instala PDFs con nombres neutros y genera sidecars
  privados.
- `tests/test_cetil_private_regression.py`: compara cada PDF con su JSON esperado y valida que no
  existan `texto_paginas` ni `raw_text` en el snapshot.

En esta máquina se instalaron localmente tres CETIL de guía desde
`C:\Users\djjav\Documents\CETILIA\docs\CETILES`. Los tres PDFs, sus tres snapshots y sus tres
sidecars están bajo `tests/fixtures_private/`, ignorados por Git. No se imprimieron nombres ni texto
extraído durante la preparación.

### B.6 Conteos

| Entorno | Resultado esperado |
|---|---|
| Checkout con los tres fixtures privados locales | 106 pruebas pasadas. |
| Checkout limpio sin fixtures privados | 103 pasadas y 1 omitida; la omisión explica que no hay CETIL privado instalado. |
| Incremento público ejecutable sin datos privados | 27 pruebas pasadas y 1 omitida. |
| Incremento local con los tres casos privados | 30 pruebas pasadas. |

## C. Comportamientos congelados

Los siguientes valores son deliberadamente literales:

| Caso | Comportamiento actual congelado |
|---|---|
| Precisión | Cálculo interno con `Decimal`, precisión global 28 y sin redondeo intermedio. |
| Periodo de un día | Produce `0` días, `SC=0` e `ISV=0`. |
| 30/31 | `2020-01-30..2020-01-31` produce `0` días. |
| Febrero común | `2021-02-28..2021-03-31` produce `33` días. |
| Febrero bisiesto | `2020-02-29..2020-03-31` produce `32` días. |
| Cambio de año | `1999-12-31..2000-01-01` produce `1` día. |
| IPC inicial | Promedio de los meses válidos disponibles del año, aunque sean menos de 12. |
| IPC final | Último periodo `YYYY-MM` válido, incluso si es futuro. |
| Duplicado mensual IPC | Conserva el último registro válido encontrado para ese mes. |
| Duplicados laborales | Son advertencia; ambas filas llegan al cálculo. |
| Solapamientos laborales | Son advertencia; los días de ambas filas se suman. |
| Contiguos CETIL | Se consolidan en una fila anual. |
| Brechas CETIL | Se conservan como varias filas del mismo año. |
| SBC | Promedio aritmético simple por fila de IBC semanal actualizado. |
| Excel | Repite las fórmulas del motor y exporta importes monetarios cuantizados a centavos como float. |

## D. Bugs conocidos congelados

### D.1 `KNOWN_BUG_FECHA_LIQUIDACION`

Solicitar `fecha_liquidacion=2025-01-31` con IPC disponible hasta `2026-01` produce IPC final
`2026-01`. El argumento llega a `_calcular_periodo()` pero no se usa. La prueba debe fallar cuando
este bug se corrija de forma deliberada en una fase posterior; entonces se versionará la expectativa,
no se relajará la comparación.

### D.2 Formato IPC con coma decimal

`"155,73"` se interpreta actualmente como `Decimal("15573")`. Los otros casos congelados son:

```text
"155.73"  -> 155.73
"1.234,56" -> 1234.56
"1,234.56" -> 1234.56
```

### D.3 Anualización legada 1987-1988

Cuando un periodo previo termina el `1987-11-06` y el siguiente es
`1987-11-07..1988-01-17`, el resultado anual actual queda:

```text
1987-01-01 .. 1987-11-07
1988-01-01 .. 1988-01-17
```

Desaparecen exactamente las 54 fechas de `1987-11-08` a `1987-12-31`, ambas inclusive. La prueba se
denomina `LEGACY_CURRENT_BEHAVIOR` y no corrige la regla.

### D.4 Advertencias no bloqueantes

Duplicados, solapamientos, brechas, años IPC incompletos y registros futuros pueden producir o no
advertencias, pero no son bloqueos generales del motor. Esta línea base conserva esa diferencia
entre `ERROR` y `ADVERTENCIA`.

### D.5 Doble implementación del Excel

El motor calcula en Python y el XLSX vuelve a expresar las fórmulas. La suite congela ambas sin
consolidarlas. Una divergencia futura se considerará una señal de revisión, no una invitación a
actualizar silenciosamente el snapshot.

## E. Casos reales todavía necesarios

Antes de declarar listo el traslado a CETILIA todavía hacen falta:

1. CETIL anonimizados de más entidades, años, versiones y estructuras tabulares.
2. PDFs con tabla parcialmente reconocida, encabezados repetidos y factores divididos en más páginas.
3. PDF escaneado, cifrado, corrupto, vacío, con extensión falsa y con límites altos de páginas/tamaño.
4. Variaciones reales de conceptos salariales, acentos, meses parciales, empates y atípicos.
5. Históricos IPC reales `.xlsx`, `.xlsm`, `.csv` y `.xls` solo si se decide soportar este último.
6. IPC con columnas ambiguas, encodings/delimitadores distintos, duplicados y meses futuros.
7. Comparación de `commercial_360_days()` contra Excel en todos los bordes de febrero y fin de mes.
8. Recalcular el XLSX en Excel/LibreOffice y comparar el resultado recalculado, no solo el valor
   cacheado por XlsxWriter.
9. Aprobación jurídica de fórmula, PPC, divisor, SBC, días, IPC anual y redondeo.

## F. Procedimiento para agregar un CETIL privado

### F.1 Reglas de privacidad

- Nunca copiar un PDF CETIL fuera de `tests/fixtures_private/` dentro del repositorio.
- Nunca usar `git add -f` sobre esa carpeta.
- Nunca pegar nombres, documentos o texto extraído en tests, logs, issues o commits.
- El JSON `.redactions.json` contiene valores sensibles de sustitución y también debe permanecer
  privado.
- El JSON `.expected.json` no contiene páginas completas ni `raw_text`; aun así permanece ignorado
  hasta que una revisión humana confirme que está anonimizado.

### F.2 Instalación/generación

Desde la raíz de AppIndemnizaciones:

```powershell
.\.venv\Scripts\python.exe -m tests.generate_cetil_private_snapshots `
  --source-dir "C:\ruta\privada\con_cetiles"
```

El generador:

1. exige que `.gitignore` contenga `tests/fixtures_private/`;
2. copia los PDFs como `case_001.pdf`, `case_002.pdf`, etc.;
3. crea `case_NNN.redactions.json` con sustituciones exactas sugeridas;
4. crea `case_NNN.expected.json` con SHA-256 y los campos solicitados;
5. excluye `texto_paginas` y cualquier clave `raw_text`.

Revisar manualmente el sidecar y el esperado sin imprimirlos en terminal. Para actualizar un snapshot
después de un cambio deliberado y aprobado:

```powershell
.\.venv\Scripts\python.exe -m tests.generate_cetil_private_snapshots `
  --private-dir tests\fixtures_private `
  --force
```

Nunca usar `--force` solo para hacer verde una regresión inesperada.

### F.3 Verificación

```powershell
git check-ignore -v tests/fixtures_private
.\.venv\Scripts\python.exe -m pytest -q tests/test_cetil_private_regression.py
git status --short
```

El estado Git no debe listar PDFs, expected JSON ni redactions JSON.

## G. Procedimiento para comparar AppIndemnizaciones y CETILIA

1. Fijar el commit/rama de cada lado y exigir working trees limpios o diffs documentados.
2. Copiar a CETILIA el fixture público
   `tests/fixtures/regression/liquidacion_service_baseline.json`, no lógica de UI.
3. Construir un adaptador CETILIA que transforme cada entrada JSON a sus modelos y emita el mismo
   esquema de resultado.
4. Comparar fechas e enteros directamente y todos los importes mediante `Decimal`, sin tolerancias ni
   redondeo para “acercar” resultados.
5. Comparar por fila: días, semanas, IPC inicial/final, IBC mensual/semanal y año.
6. Comparar totales: días, SC, SBC, PPC e ISV.
7. Ejecutar los mismos CETIL privados en ambas aplicaciones desde una ubicación local ignorada y
   comparar el snapshot canónico seudonimizado.
8. Comparar el XLSX: fechas, valores cacheados, fórmulas y resultado después de recálculo externo.
9. Clasificar cualquier diferencia como:
   - regresión accidental;
   - bug conocido que CETILIA aún reproduce;
   - cambio jurídico/funcional aprobado y versionado.
10. Nunca sobrescribir la línea base original para ocultar una diferencia; crear una nueva versión y
    conservar el vector legado.

## H. Elementos que NO deben copiarse ciegamente a CETILIA

- `fecha_liquidacion` ignorada y selección automática del último IPC.
- Parsing `"155,73" -> 15573`.
- Registros IPC futuros tratados como actuales.
- Promedio anual con meses incompletos sin bloqueo.
- Regla especial que omite 54 fechas de 1987.
- Duplicados/solapamientos como advertencias no bloqueantes.
- Promedio SBC por número de filas y el peso extra de años con varias filas.
- Implementación aproximada de `DAYS360` sin validación completa de bordes.
- Moda positiva para IBL y fallback a `Total Devengado` sin aprobación jurídica.
- Parser CETIL de columnas fijas y fallback PyMuPDF solo cuando falta `pdfplumber`.
- `texto_paginas`, `raw_text`, documento u otra PII en stores, logs o fixtures públicos.
- Fórmulas duplicadas entre Python, UI y Excel.
- Conversión `Decimal -> float` y cuantización del exportador como política monetaria implícita.
- Stores, callbacks y componentes Dash como dependencias del nuevo núcleo.
- Dependencias con solo cota mínima y launchers que reinstalan paquetes en cada inicio.
- Soporte `.xls` anunciado sin un lector instalado/probado.

## Validación integrada registrada

Después de agregar las pruebas y la infraestructura, con los tres fixtures privados locales:

```text
pytest: 106 passed, 5 warnings
ruff:   All checks passed!
```

No se hizo commit, push ni merge. La rama queda local para inspección del diff.
