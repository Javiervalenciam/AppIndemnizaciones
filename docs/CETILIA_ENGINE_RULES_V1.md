# CETILIA — reglas funcionales del motor objetivo V1

**Fecha:** 2026-08-13
**Fase:** 3B — especificación funcional, sin implementación productiva
**Estado:** borrador funcional para aprobación de las decisiones pendientes
**Fuentes:** `CETILIA_REGRESSION_BASELINE.md` y `CETILIA_ENGINE_SPEC_DISCOVERY.md`

> Una prueba de regresión demuestra el comportamiento legado; no demuestra corrección jurídica.
> Esta versión solo fija como objetivo lo declarado expresamente. Todo vacío jurídico o económico
> queda en `REVIEW_REQUIRED` y no se completa mediante inferencias.

## A. Alcance

Este documento define el comportamiento objetivo de CETILIA para ingestión y extracción CETIL,
revisión humana, normalización de historia laboral, días y semanas, IPC, salarios e IBL, cálculo de
indemnización sustitutiva, clasificación de tiempos, múltiples documentos, trazabilidad, bloqueos y
exportación. Es el contrato funcional previo a implementar el nuevo motor.

Quedan fuera de alcance en esta fase:

- código productivo, modelos ejecutables, frontend, base de datos y repositorio CETILIA;
- cambios a pruebas, snapshots, fixtures dorados o comportamiento de AppIndemnizaciones;
- reglas jurídicas finales de clasificación, bono pensional, devolución de saldos o 150 semanas;
- aprobación de la convención de días, fórmula definitiva de SBC, fórmula jurídica de IBL,
  redondeos finales o mes exacto de IPC aplicable.

Los estados normativos usados en la matriz legado → CETILIA son exclusivamente `KEEP`, `FIX`,
`BLOCK`, `REVIEW_REQUIRED` y `NOT_APPLICABLE`.

### A.1 Arquitectura objetivo

La separación funcional obligatoria es:

```text
Document ingestion
        ↓
CETIL Extractor
        ↓
Human Review
        ↓
History Normalizer
        ↓
Time Classifier
        ↓
Calculation Engine
        ↓
Decision Engine
        ↓
Excel / UI
```

Cada capa recibe y devuelve contratos tipados/versionados. Ninguna de estas capas depende de Dash;
Dash o cualquier frontend futuro solo adapta entradas y presenta salidas.

## B. Decisiones cerradas

### B.1 Registro de decisiones

| Decision ID | Descripción | Estado | Origen | Impacto |
| --- | --- | --- | --- | --- |
| `DEC-PPC-001` | `PPC = 0.0227`, global y constante para el motor actual de indemnización sustitutiva | `APPROVED` | Decisión cerrada de Fase 3B | Una sola tasa para todas las filas; no existe PPC histórico ni por periodo |
| `DEC-CALC-001` | `ISV = SBC × SC × PPC` | `APPROVED` | Especificación Fase 3B | Fórmula principal del motor matemático |
| `DEC-PREC-001` | Aritmética interna con `Decimal`, sin introducir `float` | `APPROVED` | Especificación Fase 3B | Exactitud y reproducibilidad de operandos y resultados |
| `DEC-WEEK-001` | Una semana equivale a 7 días | `APPROVED` | Especificación Fase 3B | Conversión de días a semanas y cálculo de SC |
| `DEC-IPC-001` | El IPC final nunca puede ser posterior a la fecha de liquidación/corte | `APPROVED` | Corrección funcional Fase 3B | Impide que el último registro futuro se vuelva aplicable automáticamente |
| `DEC-IPC-002` | Año IPC incompleto exige revisión; año sin IPC bloquea | `APPROVED` | Especificación Fase 3B | Evita promedios incompletos silenciosos |
| `DEC-PERIOD-001` | La segmentación anual debe conservar todos los días del rango original | `APPROVED` | Corrección funcional Fase 3B | Elimina la pérdida silenciosa de fechas |
| `DEC-DUP-001` | Duplicados exactos no se contabilizan dos veces; solapamientos no resueltos exigen revisión | `APPROVED` | Especificación Fase 3B | Evita doble conteo silencioso y conserva procedencia |
| `DEC-SBC-001` | La segmentación puramente técnica no debe cambiar el resultado; fórmula definitiva de SBC pendiente | `PARTIALLY_APPROVED` | Especificación Fase 3B | Obliga pruebas de invariancia antes de aprobar fórmula |
| `DEC-EXCEL-001` | Excel no será un segundo motor de cálculo | `APPROVED` | Especificación Fase 3B | El backend es la única fuente del resultado |
| `DEC-ARCH-001` | El núcleo y sus capas no dependen de Dash | `APPROVED` | Descubrimiento + Fase 3B | Permite cálculo y auditoría fuera de UI |

### B.2 Decisión PPC no reabrible

`DEC-PPC-001` fija exactamente:

```text
PPC = 0.0227
```

Su alcance es global para el motor actual de indemnización sustitutiva. Es constante para todas las
filas y se usa en `ISV = SBC × SC × PPC`. En esta fase no se analiza, recalcula, cuestiona ni hace
variable; no se crea PPC histórico, por periodo ni tabla de tasas, y no se propone `0.022725`.

## C. Reglas KEEP

### C.1 Reglas conservadas

- PPC exacto, global y constante: `Decimal("0.0227")` en la frontera matemática.
- Fórmula principal: `ISV = SBC × SC × PPC`.
- Aritmética interna con `Decimal`; ningún operando matemático nace o pasa por `float`.
- Una semana equivale a 7 días. Dada una cantidad de días ya aprobada,
  `semanas = Decimal(dias) / Decimal(7)`.
- Brechas reales no se rellenan automáticamente.
- Periodos contiguos pueden consolidarse únicamente bajo las condiciones de la sección G.
- Las heurísticas salariales existentes se conservan como sugerencias, nunca como decisión jurídica.
- Toda ejecución conserva `source_document_hash`, `extraction_version`, `normalization_version`,
  `legal_rules_version`, `calculation_version`, `ipc_dataset_version` y `calculated_at`.

### C.2 Matriz legado → CETILIA

| ID | Componente | Comportamiento legado | Estado | Comportamiento objetivo CETILIA | Motivo | Prueba legado | Prueba futura necesaria |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MAP-MATH-001` | Precisión | `Decimal`, precisión 28 y sin redondeo intermedio en el motor | `KEEP` | Usar `Decimal` de extremo a extremo; precisión y redondeo quedan versionados | Evitar pérdida y hacer reproducible el cálculo | `test_liquidacion_calcula_sbc_sc_y_aportes_sin_redondeo_intermedio` | Propiedad que rechace `float` y reproduzca operandos exactos |
| `MAP-MATH-002` | Semana/SC | Días y SC se dividen entre 7 | `KEEP` | `1 semana = 7 días`; SC conserva esta conversión una vez aprobados los días | Decisión cerrada | Suite dorada y pruebas Excel | Propiedad `weeks = days / 7` para cada convención aprobada |
| `MAP-MATH-003` | ISV | `SBC × SC × PPC` | `KEEP` | Conservar la fórmula exacta | Decisión cerrada | `test_liquidacion_calcula_sbc_sc_y_aportes_sin_redondeo_intermedio` | Vector objetivo con entradas versionadas y traza de operandos |
| `MAP-MATH-004` | IBC actualizado | `IBL × (IPC final / IPC inicial)` | `REVIEW_REQUIRED` | Conservarla como comportamiento documentado hasta aprobación jurídica expresa | No fue cerrada como regla objetivo por esta fase | Pruebas de `LiquidacionService` y oráculo dorado | Vector jurídico aprobado con trazabilidad de cada operando |
| `MAP-MATH-005` | IBC semanal | Divide IBC actualizado por `4.345` | `REVIEW_REQUIRED` | No fijar el divisor como norma por mera regresión | La equivalencia mensual/semanal requiere aprobación | Pruebas de servicio, Excel y oráculo dorado | Comparar divisor y unidad contra regla autorizada |
| `MAP-PPC-001` | PPC | Valor global `0.0227` para todas las filas | `KEEP` | `Decimal("0.0227")`, global y constante | `DEC-PPC-001` | Oráculo dorado y regresión Excel | Confirmar mismo PPC en cada fila y total, sin tabla temporal |
| `MAP-IPC-001` | Parsing IPC | `"155,73"` se interpreta como `15573` | `FIX` | Interpretar como `Decimal("155.73")` mediante una única regla de parsing | Corrige cambio de magnitud | `test_current_behavior_ipc_text_number_formats` | Tabla latina/internacional, ambiguos y entradas inválidas |
| `MAP-IPC-002` | IPC final | Se toma el último periodo válido, incluso futuro | `FIX` | Separar último periodo del dataset de periodo aplicable; excluir posteriores al corte | Fecha futura no puede controlar el cálculo | `test_current_behavior_ipc_future_record_becomes_current` | Dataset con registros antes, en y después del corte |
| `MAP-IPC-003` | Fecha de liquidación | Se recibe pero no afecta el IPC final | `FIX` | `liquidation_date` obligatoria y auditada controla el límite superior | El parámetro legado es inefectivo | `test_known_bug_fecha_liquidacion_uses_latest_ipc_instead_of_requested_date` | Verificar que cambiar el corte cambia solo selecciones permitidas |
| `MAP-IPC-004` | IPC inicial | Promedio simple de meses válidos disponibles del año | `REVIEW_REQUIRED` | Documentar el promedio; con 12 meses es `VALID`, con menos exige revisión y sin meses bloquea; fórmula alternativa no definida | La prueba legada no valida la regla jurídica | `test_get_annual_average_ipc_calcula_promedio_anual` | Aprobación jurídica y casos 12/11/0 meses |
| `MAP-IPC-005` | Mes IPC duplicado | Se conserva el último registro válido encontrado | `REVIEW_REQUIRED` | Detectar conflicto, conservar fuentes y no escoger silenciosamente hasta regla/aprobación | El orden del archivo no prueba vigencia | `test_current_behavior_ipc_duplicate_month_keeps_last_valid_row` | Duplicados iguales, distintos, con fuente/fecha de publicación |
| `MAP-IPC-006` | Histórico IPC inválido | Filas inválidas se omiten; si no queda histórico válido ocurre error | `BLOCK` | Bloquear si no existe dataset versionado con al menos un registro válido aplicable | No puede calcularse indexación sin fuente válida | Pruebas de vacíos y `test_ipc_not_found_error` | Dataset vacío, corrupto, no versionado y sin registros al corte |
| `MAP-PERIOD-001` | Anualización | El cruce 1987-1988 puede perder 54 fechas | `FIX` | Particionar sin pérdida y probar igualdad de días original/segmentos | Corrige pérdida silenciosa | `test_legacy_current_behavior_cross_year_period_loses_late_1987_dates` | Propiedad de conservación para cruces de año y varios años |
| `MAP-PERIOD-002` | Duplicado exacto | Advierte, pero ambas filas se calculan | `FIX` | Detectar, marcar, conservar fuentes y producir una sola representación resuelta | Evita doble conteo | `test_current_behavior_duplicate_periods_warn_but_both_are_calculated` | Duplicados intra/interdocumento, idénticos y conflictivos |
| `MAP-PERIOD-003` | Solapamiento | Advierte, pero suma días de ambas filas | `FIX` | `REVIEW_REQUIRED` hasta resolver el tramo; no calcularlo silenciosamente | Evita doble conteo no autorizado | `test_current_behavior_overlapping_periods_warn_but_days_are_summed` | Solape parcial, total, entre entidades y con salarios distintos |
| `MAP-PERIOD-004` | Contiguos | Segmentos CETIL contiguos del mismo año se consolidan | `KEEP` | Consolidación condicional: misma vinculación, sin interrupción ni conflictos de entidad/salario | Reduce segmentación técnica sin borrar cambios reales | `test_current_behavior_contiguous_cetil_periods_are_consolidated` | Matriz de condiciones permitidas/prohibidas |
| `MAP-PERIOD-005` | Brechas | Filas con brecha permanecen separadas | `KEEP` | Conservar la brecha como `HistoryIssue`; jamás rellenarla | No inventar historia laboral | `test_current_behavior_gap_keeps_multiple_rows_for_same_year` | Brechas de 1 día, mes, año y entre documentos |
| `MAP-DAY-001` | `commercial_360` | Fórmula aproximada 30/360, sin sumar un día | `REVIEW_REQUIRED` | No fijar resultado jurídico hasta aprobación de convención y extremos | Caracterización no equivale a validez jurídica | Suite dorada de 8 casos | Oráculo jurídico contra calendario y Excel `DAYS360` |
| `MAP-DAY-002` | `calendar` | `(end - start).days`, extremo final no incluido | `REVIEW_REQUIRED` | Convención e inclusión de extremos pendientes | No existe aprobación jurídica | Pruebas de servicio | Casos de un día, meses, febrero y bisiesto |
| `MAP-DAY-003` | Excel `DAYS360` | Recalcula días independientemente de Python | `FIX` | Excel recibe días calculados; una fórmula visible es solo explicativa y debe corresponder a versión | Evitar dos motores | `test_current_excel_formulas_duplicate_engine_formulas_by_design` | Paridad backend/exportación sin recálculo independiente |
| `MAP-SBC-001` | SBC | Promedio simple de `IBC_semanal_actualizado` por número de filas | `REVIEW_REQUIRED` | Fórmula definitiva pendiente; exigir invariancia frente a segmentación técnica | El número de filas puede cambiar el resultado | Oráculo dorado y prueba de SBC | Casos A-D de la sección L |
| `MAP-IBL-001` | Sugerencia IBL | Moda positiva de asignación básica; fallback a total devengado | `KEEP` | Conservar solo como sugerencia `AUTO_EXTRACTED` con evidencia y confianza | Aprovecha extracción sin convertirla en verdad jurídica | Pruebas del extractor de moda/fallback | Ambigüedad, empate, atípicos y corrección humana |
| `MAP-IBL-002` | Decisión IBL | Valor editable pasa al motor con validación `> 0` | `REVIEW_REQUIRED` | Exigir `ibl_source`, `ibl_value`, `ibl_method`, `ibl_confidence`, `ibl_review_state`; fórmula jurídica pendiente | El origen y método no quedan estructurados | Normalizador/validadores/oráculo | Estado confirmado/corregido y bloqueo por ausencia |
| `MAP-INPUT-001` | Historia | Lista vacía provoca error | `BLOCK` | Una historia normalizada vacía no puede calcularse | No existe objeto material de cálculo | Pruebas de servicio | Cierre de `CalculationInput` rechazado con historia vacía |
| `MAP-INPUT-002` | Fechas | Fecha final anterior a inicial provoca error | `BLOCK` | Fechas inválidas o invertidas impiden normalizar/calcular | Un rango inválido no admite interpretación silenciosa | `test_fecha_invalida` y `test_fecha_inicio_posterior_a_fecha_fin` | Ausentes, inválidas, invertidas y fuera de esquema |
| `MAP-INPUT-003` | IBL ausente/no positivo | Validadores y servicio rechazan valor inexistente o `<= 0` | `BLOCK` | IBL requerido inexistente/no aprobado bloquea el periodo | La fórmula necesita una base válida | Pruebas de IBL vacío/no numérico/no positivo | Ausente, rechazado y sugerido sin confirmar |
| `MAP-EXTRACT-001` | Extracción CETIL | Obtiene campos documentales con confianza global y rutas desiguales | `KEEP` | Mantener capacidades como extracción, con `SourceRef`, confianza y revisión por campo | Separar observación de conclusión | `test_cetil_extractor.py` y regresión privada | Variantes reales, OCR, tabla rota y campo por campo |
| `MAP-EXTRACT-002` | Documento ilegible | No existe un contrato integral de recuperación/bloqueo | `BLOCK` | PDF ilegible sin extracción recuperable no produce historia calculable | No hay evidencia documental utilizable | Casos reales aún pendientes en la línea base | PDF escaneado, cifrado, corrupto, vacío y extensión falsa |
| `MAP-PRIV-001` | PII de extracción | `raw_text` y texto por página existen en salida; fixtures privados los excluyen | `BLOCK` | Impedir publicación/persistencia insegura; usar referencia segura y hash | Proteger datos personales y texto documental | Regresión CETIL privada | Prueba negativa de PII/texto completo en logs, repositorio y fixtures públicos |
| `MAP-MULTI-001` | Múltiples CETIL | UI conserva un solo documento activo y reemplaza el anterior | `FIX` | 1 persona → N CETIL → N vinculaciones → una historia versionada | La historia puede requerir varias fuentes | Pruebas de estado de sesión | Asociación de identidad, conflictos, actualización y complementos |
| `MAP-CLASS-001` | Clasificación | El motor no recibe clasificación de tiempos | `REVIEW_REQUIRED` | Contrato explícito; incertidumbre = `DESCONOCIDO` + revisión | Faltan reglas jurídicas de clasificación | No existe prueba de motor | Casos con evidencia suficiente, insuficiente y contradictoria |
| `MAP-TRACE-001` | Trazabilidad | No hay versiones integrales ni auditoría por ejecución | `FIX` | Cadena fuente → extracción → revisión → normalización → regla → operación → resultado | Reproducibilidad y explicación | Pruebas parciales de serialización/Excel | Reconstrucción exacta desde `AuditTrail` |
| `MAP-EXCEL-001` | Excel | Duplica fórmulas y convierte importes cacheados a `float` | `FIX` | Exportar resultado del backend, versiones y fuentes; sin lógica independiente | Evitar divergencia y precisión implícita | Regresión Excel | Libro trazable que coincida con resultado serializado |
| `MAP-UI-001` | Dash | Callbacks construyen entradas y el flujo depende de stores Dash | `NOT_APPLICABLE` | Las capas de dominio no dependen de Dash; la UI será adaptador futuro | Dash no pertenece al núcleo objetivo | Pruebas de callbacks/UI | Prueba de motor sin importar Dash |
| `MAP-PPC-002` | PPC histórico | No existe | `NOT_APPLICABLE` | No crear PPC histórico, por periodo ni tabla de tasas en este alcance | Decisión cerrada | No aplica | Prueba negativa de ausencia de selección temporal PPC |

## D. Bugs FIX

### D.1 Regla única de parsing numérico latino/internacional

El futuro parser recibe el valor original, el campo de origen y, cuando exista, el locale o esquema
de la fuente. Su salida es `Decimal` o una incidencia tipada; nunca `float`.

1. Quitar solo espacios y símbolos permitidos por el esquema; validar signo y caracteres restantes.
2. Si aparecen `.` y `,`, el separador más a la derecha es decimal y los anteriores son agrupadores
   de miles. La agrupación debe ser válida.
3. Si aparece un solo tipo de separador una vez y quedan una o dos cifras a la derecha, es decimal.
4. Si aparece repetido, solo es agrupador cuando todos los grupos posteriores tienen tres cifras;
   en otro caso la entrada es inválida.
5. Una única marca con tres cifras a la derecha (`1,234` o `1.234`) es ambigua sin locale/esquema:
   produce `REVIEW_REQUIRED`; no se adivina.
6. El signo se aplica después de normalizar y el resultado se construye desde texto canónico.

Resultados obligatorios:

| Entrada | Salida |
| --- | --- |
| `155,73` | `Decimal("155.73")` |
| `155.73` | `Decimal("155.73")` |
| `1.234,56` | `Decimal("1234.56")` |
| `1,234.56` | `Decimal("1234.56")` |

### D.2 Fecha de liquidación e IPC final

`liquidation_date` será obligatoria. El futuro motor debe recibir además:

- `ipc_dataset_version` y hash/origen del dataset;
- registros IPC con `period`, `value: Decimal`, fuente y, si existe, `published_on`/`available_on`;
- `ipc_dataset_latest_period`, como metadato descriptivo;
- `ipc_applicable_period`, `ipc_final_value` y la regla o aprobación humana que los seleccionó.

Invariantes: `ipc_applicable_period` nunca es posterior al corte; un registro futuro nunca se vuelve
final por ser el último del archivo; periodo, valor, fuente, regla y corte quedan en auditoría. La
regla sobre cuál mes exacto es jurídicamente aplicable y cómo interviene la fecha de publicación
permanece `REVIEW_REQUIRED`.

### D.3 Conservación de días al segmentar

Ninguna anualización puede eliminar silenciosamente fechas entre `fecha_inicio` y `fecha_fin`. Debe
cumplirse, bajo la misma convención de días aprobada:

```text
SUMA_DIAS_SEGMENTOS_NORMALIZADOS = DIAS_PERIODO_ORIGINAL
```

La única excepción son interrupciones explícitas, con rango, fuente, regla y decisión documentados.
La unión ordenada de los segmentos debe reconstruir el rango original menos esas interrupciones,
sin huecos ni duplicidad interna.

### D.4 Doble conteo y segundo motor Excel

Los duplicados exactos se representan una sola vez después de su resolución, preservando todas las
fuentes. Los solapamientos no resueltos no entran silenciosamente al cálculo. Excel deja de decidir
días, IPC, SBC o ISV de forma independiente: presenta el resultado del backend.

## E. Reglas BLOCK

Una condición `BLOCK` impide cerrar `CalculationInput` o ejecutar un cálculo definitivo. No se
convierte en advertencia para continuar.

- PDF ilegible sin extracción recuperable.
- Fechas ausentes o inválidas en un periodo seleccionado.
- `fecha_fin < fecha_inicio`.
- IBL requerido inexistente o no aprobado para el cálculo.
- Año de IPC completamente inexistente para un periodo seleccionado.
- Historia normalizada vacía.
- Identidad conflictiva entre documentos sin resolver.
- Dataset IPC inexistente, no versionado o sin ningún registro válido utilizable.
- Conflicto no resuelto que haga imposible determinar qué persona o historia se calcula.

### E.1 Catálogo de severidades

| Nivel | Efecto funcional | Ejemplos mínimos |
| --- | --- | --- |
| `ERROR` | Falla técnica o violación del contrato; no hay resultado válido | Esquema de entrada corrupto, versión irresoluble, fallo de integridad/hash, operación matemática imposible |
| `BLOCK` | Validación de dominio impide calcular hasta corregir o aportar evidencia | PDF irrecuperable, fechas inválidas, IBL ausente, año IPC sin datos, historia vacía, identidad conflictiva |
| `REVIEW_REQUIRED` | Requiere decisión humana registrada; el cálculo definitivo no usa el dato ambiguo | Solape, duplicado conflictivo, IPC incompleto, IBL ambiguo, clasificación desconocida, entidad contradictoria |
| `WARNING` | Se puede calcular porque no cambia el dato matemático aprobado; queda visible y auditado | Advertencia documental no material, campo opcional ausente |
| `INFO` | Explica una transformación o selección sin exigir acción | Consolidación permitida, versión usada, conteo de documentos o segmentos |

## F. Reglas REVIEW_REQUIRED

Exigen revisión y resolución explícita antes de usar el dato afectado en un cálculo definitivo:

- solapamientos laborales;
- duplicados con valores, entidades, fechas, salarios o roles en conflicto;
- año IPC con menos de 12 meses válidos;
- mes IPC duplicado con valores o procedencia conflictiva;
- mes exacto de IPC final mientras no exista regla aprobada;
- IBL ambiguo, empatado, atípico, inferido o sin concepto jurídico aprobado;
- clasificación `DESCONOCIDO`;
- entidad contradictoria o rol de entidad no determinado;
- discrepancia significativa entre días declarados por CETIL y días calculados;
- convención de días e inclusión de extremos;
- fórmula definitiva y ponderación del SBC;
- política de redondeo monetario final;
- asociación de documentos cuando la identidad no esté confirmada.

`requires_review=true` nunca se convierte silenciosamente en aprobación ni se limpia por una
transformación posterior.

## G. Normalización de periodos

La normalización produce una `NormalizedHistory` inmutable y versionada. Cada segmento conserva
vinculación, entidad/rol, salarios, clasificación, fuentes y resoluciones.

### G.1 Duplicados, solapamientos, contiguos y brechas

| Caso | Detección | Acción | Condición de salida |
| --- | --- | --- | --- |
| Duplicado exacto | Mismo rango, vinculación y valores relevantes | Marcar grupo, conservar todas las `source_refs`, evitar doble conteo | Una representación normalizada una vez resuelto |
| Duplicado conflictivo | Rango equivalente con diferencias materiales | `REVIEW_REQUIRED` | Resolución con valor elegido, motivo, actor y fuentes |
| Solapamiento | Intersección no vacía entre rangos no resueltos | No sumar; crear `HistoryIssue` | Decisión explícita sobre cada subtramo |
| Contiguo | Fin/inicio adyacentes según convención aprobada | Puede consolidarse | Misma vinculación, sin interrupción, conflicto de entidad ni cambio salarial material |
| Brecha | Rango entre segmentos sin cobertura | Conservarla, nunca rellenar | `HistoryIssue` con límites y fuentes relacionadas |

### G.2 Invariantes de normalización

- Ningún día fuente desaparece ni se duplica por una transformación técnica.
- Toda interrupción excluida es explícita y trazable.
- Consolidar no borra cambios económicos, jurídicos, de entidad, clasificación o fuente.
- Dividir por año no crea ni elimina tiempo.
- El orden o cantidad de documentos no cambia la historia resuelta.
- La procedencia es muchos-a-uno: una fila normalizada puede conservar varias fuentes.
- Una brecha no se interpreta como ausencia laboral, no cotización ni tiempo desconocido sin regla.

## H. Días y semanas

La equivalencia de 7 días por semana está aprobada. La convención que determina los días todavía no.

| Caso | Resultado legado | Riesgo | Resultado objetivo definido | Estado |
| --- | --- | --- | --- | --- |
| `commercial_360` general | Fórmula aproximada: años×360 + meses×30 + ajuste de días | Puede diferir de otras variantes 30/360 y de Excel | No definido jurídicamente; debe identificarse por regla/versionado | `REVIEW_REQUIRED` |
| `calendar` | `(fecha_fin - fecha_inicio).days` | Excluye extremo final | No definido jurídicamente | `REVIEW_REQUIRED` |
| Excel `DAYS360` | Fórmula independiente en exportación | Puede divergir de Python | No recalcula; muestra el valor backend y, si procede, explicación | `FIX` |
| Periodo de un día | 0 días | Puede excluir un día realmente certificado | Pendiente de regla sobre inclusión de extremos | `REVIEW_REQUIRED` |
| Borde 30/31 | `2020-01-30..2020-01-31` = 0 días | Ajuste de fin de mes no aprobado | Pendiente de convención | `REVIEW_REQUIRED` |
| Febrero común | `2021-02-28..2021-03-31` = 33 días | Tratamiento de febrero no aprobado | Pendiente de convención | `REVIEW_REQUIRED` |
| Febrero bisiesto | `2020-02-29..2020-03-31` = 32 días | Tratamiento bisiesto no aprobado | Pendiente de convención | `REVIEW_REQUIRED` |
| Cambio de año | `1999-12-31..2000-01-01` = 1 día | Inclusión de extremos no aprobada | Pendiente de convención | `REVIEW_REQUIRED` |
| División por año | Puede perder 54 fechas en caso legado | Pérdida silenciosa | Conservar exactamente los días del periodo original | `FIX` |
| Conversión a semanas | `dias / 7` | Depende de que los días sean correctos | `Decimal(dias) / Decimal(7)` | `KEEP` |

Hasta aprobar la convención, los resultados anteriores son oráculos de legado, no expectativas del
motor objetivo. La prueba futura debe contrastar `commercial_360`, `calendar` y Excel `DAYS360` en
todos los bordes y registrar la regla finalmente aprobada.

## I. IPC

### I.1 IPC inicial

Comportamiento legado documentado: promedio aritmético simple de los meses IPC válidos disponibles
del año, después de conservar un registro válido por mes. Esto incluye promediar años incompletos.

| Disponibilidad anual | Estado de validación objetivo | Acción |
| --- | --- | --- |
| 12 meses válidos | `VALID` | El promedio queda disponible, sujeto a aprobación de la fórmula jurídica |
| 1 a 11 meses válidos | `REVIEW_REQUIRED` | Mostrar meses presentes/ausentes; no continuar silenciosamente |
| 0 meses válidos | `BLOCK` | No calcular el periodo |

No se define en V1 una fórmula alternativa para años incompletos. Los duplicados mensuales conservan
todas las fuentes; la elección de valor conflictivo requiere revisión.

### I.2 IPC final

El contrato separa:

```text
ipc_dataset_latest_period != necesariamente ipc_applicable_period
```

Cada cálculo registra `liquidation_date`, `ipc_final_period`, `ipc_final_value` e
`ipc_dataset_version`. También registra `ipc_dataset_latest_period`, fuente del registro final,
fecha de publicación/disponibilidad cuando exista y regla/aprobación de selección. Un registro
posterior a la fecha de corte queda fuera de selección automática.

La definición jurídica del mes exacto aplicable sigue `REVIEW_REQUIRED`; esta incertidumbre no
autoriza volver al “último registro del archivo”.

## J. IBL y salarios

Extracción y decisión de IBL son capas distintas:

```text
conceptos y valores extraídos -> sugerencia -> revisión humana/regla -> IBL aprobado -> cálculo
```

El extractor puede detectar asignación básica mensual, total devengado, otros factores, valores
mensuales, conceptos y periodicidad. La moda, el fallback y la detección de atípicos permanecen como
herramientas de sugerencia.

Cada decisión IBL contiene:

| Campo | Regla |
| --- | --- |
| `ibl_source` | Referencias a documento, página, tabla/fila/campo o corrección manual |
| `ibl_value` | `Decimal`; ausente si no puede determinarse |
| `ibl_method` | Heurística identificada, regla jurídica versionada o selección manual |
| `ibl_confidence` | Confianza de extracción/decisión; no sustituye aprobación |
| `ibl_review_state` | `AUTO_EXTRACTED`, `CONFIRMED`, `CORRECTED` o `REVIEW_REQUIRED` |

Una moda no es una verdad jurídica. Un valor ambiguo debe revisarse antes del cálculo. Toda
corrección conserva valor anterior, valor nuevo, motivo, actor, instante y evidencia. La fórmula
jurídica definitiva del IBL y los conceptos que lo integran permanecen pendientes.

## K. PPC

PPC queda regulado exclusivamente por `DEC-PPC-001`:

```text
PPC = Decimal("0.0227")
```

Es global, constante, común a todas las filas y se usa en `ISV = SBC × SC × PPC`. No se recibe por
periodo, no se consulta por fecha, no tiene dataset histórico y no se deriva del CETIL.

## L. SBC

El legado calcula:

```text
SBC = SUM(IBC_semanal_actualizado) / numero_de_filas
```

La fórmula definitiva permanece `REVIEW_REQUIRED`. Antes de aprobarla deben ejecutarse pruebas de
invariancia con el mismo contenido económico y jurídico:

| Caso conceptual | Representación | Resultado legado esperado | Criterio objetivo de la prueba |
| --- | --- | --- | --- |
| A | Periodo continuo en una fila con valor semanal `W` | `SBC = W` | Caso base |
| B | Mismo periodo y salarios en dos filas técnicamente iguales | `(W + W) / 2 = W` si todos los operandos coinciden | Debe ser idéntico a A |
| C | Mismo periodo dividido solo por año | Promedia valores de cada fila; puede diferir si IPC inicial u otro operando cambia | Debe ser idéntico a A cuando nada económico/jurídico cambió |
| D | Mismo periodo dividido por cambios salariales reales | Promedia filas con igual peso, con independencia de duración | Puede diferir, pero solo según fórmula económica/jurídica aprobada |

Principio arquitectónico obligatorio:

```text
La segmentación puramente técnica del mismo periodo no debe alterar
el resultado matemático salvo que exista una variable económica
o jurídica que realmente haya cambiado.
```

Las pruebas deben permutar orden, división anual, consolidación y cantidad de filas, comparar
intermedios y señalar cuál variable material justifica cualquier diferencia.

## M. Clasificación de tiempos

El contrato usa solo `COTIZADO`, `PUBLICO_NO_COTIZADO`, `PUBLICO_COTIZADO` y `DESCONOCIDO`.

Cada tramo clasificado guarda:

```text
classification
start_date
end_date
entity
administrator
source_refs
confidence
requires_review
classification_method
```

`classification_method` es `MANUAL` o una regla versionada. Si la evidencia no basta:

```text
classification = DESCONOCIDO
requires_review = true
```

No se infiere clasificación únicamente porque la entidad sea pública, aparezca una AFP, se lea
`SI` en aportes o falte un fondo. La clasificación es independiente del cálculo matemático y no
constituye todavía una decisión de prestación.

## N. Múltiples CETIL

El modelo objetivo es:

```text
1 persona
    -> N certificados CETIL
    -> N vinculaciones
    -> 1 historia normalizada versionada
```

Reglas funcionales:

- Asociar por identidad documental revisada; el nombre es dato de contraste, no clave de unión.
- Si los identificadores de persona son conflictivos, aplicar `BLOCK` hasta resolver.
- Detectar periodos repetidos dentro y entre documentos antes de normalizar.
- Conservar documentos complementarios como fuentes simultáneas, sin escoger uno por orden.
- Marcar contradicciones por campo, rol, periodo y fuente; no sobrescribirlas silenciosamente.
- Un documento actualizado no borra el anterior: ambos conservan hash, versión, fecha y relación de
  actualización; la precedencia requiere regla o revisión.
- Mantener separadas entidad certificadora, empleadora, administradora y responsable declarada o
  decidida.
- El orden de carga no altera la historia resuelta.

Nunca se unen documentos únicamente por similitud de nombres.

## O. Revisión humana

Se conserva la distinción:

```text
dato extraído != dato confirmado != conclusión jurídica
```

Cada campo extraído conserva valor original, valor normalizado propuesto, `SourceRef`, confianza,
estado y advertencias. Los estados de revisión por campo son `PENDING`, `CONFIRMED`, `CORRECTED` y
`REJECTED`; el IBL usa adicionalmente los estados funcionales de la sección J.

La revisión humana debe ocurrir antes de calcular cuando el dato sea material o ambiguo. Confirmar o
corregir crea un evento append-only. Rechazar un dato no elimina la extracción original. Resolver
una incidencia exige actor, instante, decisión, motivo y evidencia.

Campos extraíbles dentro de este contrato: persona, número CETIL, entidad certificadora, entidad
empleadora, fechas, cargo, tipo de vinculación, tipo de empleado, aportes a pensión/salud/riesgos,
fondo, entidad responsable, días declarados, interrupciones, horas, salarios y factores salariales.

## P. Trazabilidad

Toda ejecución explica:

```text
Documento
  -> Dato extraído
  -> Dato confirmado/corregido
  -> Periodo normalizado
  -> Regla aplicada
  -> Operación matemática
  -> Resultado
```

### P.1 Contratos mínimos

| Contrato | Contenido mínimo |
| --- | --- |
| `SourceRef` | `document_id`, página, tabla/fila/campo o locator, hash del valor |
| `ManualOverride` | ruta del campo, antes, después, motivo, actor, instante, `source_refs` |
| `AuditTrail` | hashes de documentos, IDs de entrada/resultado/decisión, versiones, eventos, hashes y entorno |
| `RuleEvaluation` | `rule_id`, hechos/hash de hechos, resultado, explicación, fuentes, instante |
| `CalculationInput` | persona/historia, corte, periodos seleccionados, contexto, convención, IPC/reglas/versiones, overrides, hash |
| `CalculationResult` | resultados por periodo, días/semanas, SC, SBC, PPC, ISV, intermedios, reglas, advertencias, hash |
| `DecisionResult` | resultado futuro, cálculo base, evaluaciones, entidad/importe si aplica, revisión y versión |

### P.2 Identificadores obligatorios

Cada ejecución incluye, como mínimo: `source_document_hash`, `extraction_version`,
`normalization_version`, `legal_rules_version`, `calculation_version`, `ipc_dataset_version` y
`calculated_at` con zona horaria. Las versiones son resolubles a manifiestos inmutables; no basta
una etiqueta libre como `v1`.

Los documentos con PII y su texto completo no se guardan en repositorio, logs, mensajes ni fixtures
públicos. La referencia segura y el hash permiten comprobar integridad sin exponer contenido.

## Q. Motor de cálculo

El motor matemático recibe exclusivamente una entrada cerrada, normalizada, revisada y versionada.
No extrae PDF, no decide identidad, no resuelve solapamientos, no infiere clasificación y no depende
de UI.

Contrato funcional mínimo de entrada:

- `calculation_input_id`, `person_id`, `normalized_history_id`;
- `liquidation_date` obligatoria;
- periodos seleccionados y decisiones IBL;
- convención de días y reglas versionadas, cuando sean aprobadas;
- dataset IPC versionado y selección aplicable auditada;
- precisión/contexto Decimal y política de redondeo;
- overrides humanos y hash canónico.

Salida mínima: detalle por periodo con fuentes, días, semanas, IBL, IPC inicial/final, IBC actualizado,
IBC semanal, operandos, reglas; totales `total_days`, SC, SBC, PPC e ISV; incidencias, versiones,
instante y hash.

Reglas ya cerradas:

```text
weeks = Decimal(days) / Decimal(7)
SC = Decimal(total_days) / Decimal(7)
PPC = Decimal("0.0227")
ISV = SBC × SC × PPC
```

La convención de días, la fórmula definitiva SBC, el IBL jurídico, el divisor mensual/semanal y la
política de redondeo final no quedan aprobados por reproducir el legado.

## R. Motor de decisión

Es una capa independiente del motor matemático. Su contrato deja preparados estos resultados:

```text
BONO_PENSIONAL
INDEMNIZACION_SUSTITUTIVA
DEVOLUCION_SALDOS
NO_APLICA
REQUIERE_REVISION
```

Recibe un `CalculationResult` inmutable y hechos jurídicos versionados; devuelve `DecisionResult`
con `RuleEvaluation` por regla. En esta fase no se programa ni se especifica la regla de 150 semanas,
reglas de bono, régimen, traslados, responsabilidad o clasificación final.

## S. Excel

Principio obligatorio:

```text
Excel NO será un segundo motor de cálculo.
```

El backend produce el resultado. El contrato de exportación contiene:

- identificadores y hashes de `CalculationInput`, `CalculationResult` y, si existe,
  `DecisionResult`;
- valores exactos de resultados e intermedios serializados sin introducir una política matemática
  distinta;
- `source_document_hashes`, números CETIL de presentación segura y `source_refs` pertinentes;
- todas las versiones, `liquidation_date`, periodo/valor IPC final y `calculated_at`;
- incidencias, revisiones, reglas aplicadas y explicación de operaciones;
- esquema y versión de exportación.

Las fórmulas solo pueden mostrarse para auditoría y deben ser explicativas del resultado ya
calculado. No contienen constantes independientes, no seleccionan IPC, no redefinen días/SBC/ISV y
no sustituyen el valor del backend. El exportador no decide reglas ni modifica el resultado.

## T. Invariantes del sistema

1. `PPC == Decimal("0.0227")` en todas las filas y en el total.
2. `ISV == SBC × SC × PPC` bajo el contexto Decimal versionado.
3. Ningún `float` entra en el motor matemático.
4. `weeks == Decimal(days) / Decimal(7)`.
5. La segmentación técnica no altera el resultado cuando no cambia una variable material.
6. La suma de días segmentados equivale a los días originales, salvo interrupciones explícitas.
7. Ningún duplicado exacto se contabiliza dos veces.
8. Ningún solapamiento no resuelto se suma silenciosamente.
9. Ninguna brecha se rellena o clasifica automáticamente.
10. `ipc_applicable_period` nunca es posterior a `liquidation_date`.
11. El último periodo del dataset no es por sí solo el IPC aplicable.
12. Un año sin IPC bloquea; uno incompleto no pasa silenciosamente.
13. Un valor extraído nunca se vuelve confirmado ni conclusión jurídica por transformación implícita.
14. Una clasificación incierta es `DESCONOCIDO` y requiere revisión.
15. La identidad se confirma documentalmente; nunca por similitud nominal únicamente.
16. Toda corrección y resolución conserva antes, después, actor, instante, motivo y fuentes.
17. Todo resultado es reproducible desde entrada, datasets, reglas, versiones e intermedios.
18. Excel y UI consumen el resultado; no crean un cálculo alternativo.
19. Ninguna capa del núcleo depende de Dash.
20. Los documentos con PII y su texto completo no se filtran a repositorio, logs o fixtures públicos.

## U. Pruebas futuras necesarias

| ID | Área | Escenario | Aserción objetivo |
| --- | --- | --- | --- |
| `TST-NUM-001` | Parsing | `155,73`, `155.73`, `1.234,56`, `1,234.56` | `Decimal` exactos esperados |
| `TST-NUM-002` | Parsing | Separador ambiguo, agrupación inválida, signo y espacios | Revisión o error tipado; nunca magnitud inventada |
| `TST-IPC-001` | IPC inicial | 12, 11, 1 y 0 meses | `VALID`, `REVIEW_REQUIRED`, `REVIEW_REQUIRED`, `BLOCK` |
| `TST-IPC-002` | IPC final | Registros anteriores, iguales y posteriores al corte | Ningún posterior es aplicable |
| `TST-IPC-003` | IPC duplicado | Mismo mes con valores iguales/distintos y fuentes | Procedencia completa; conflicto no se resuelve por orden |
| `TST-PER-001` | Conservación | Cruces de 1 y N años, incluido 1987-1988 | Suma de días segmentados = días originales |
| `TST-PER-002` | Duplicado | Intra/interdocumento, exacto y conflictivo | Una sola representación o revisión, sin doble conteo |
| `TST-PER-003` | Solape | Parcial, total, entidades y salarios distintos | No entra al cálculo hasta resolución |
| `TST-PER-004` | Contiguos/brechas | Todas las condiciones de consolidación | Solo consolida cuando cada condición se cumple; no rellena brechas |
| `TST-DAY-001` | Días | Un día, 30/31, febrero común/bisiesto, año nuevo | Resultado coincide con la regla jurídica aprobada |
| `TST-DAY-002` | Convenciones | Python aprobado vs Excel `DAYS360`/calendario | Divergencias visibles; Excel no reemplaza backend |
| `TST-SBC-001` | Invariancia | Casos A, B y C equivalentes | Mismo SBC y mismo ISV |
| `TST-SBC-002` | Cambio real | Caso D con cambio salarial | Solo cambia según fórmula aprobada y variable trazada |
| `TST-IBL-001` | IBL | Moda, empate, atípico, fallback, corrección | Sugerencia no confirmada no se usa silenciosamente |
| `TST-MULTI-001` | Múltiples CETIL | Complementarios, actualizados, contradictorios y orden permutado | Historia estable, fuentes preservadas, conflictos explícitos |
| `TST-ID-001` | Identidad | Mismo nombre/distinto documento y variantes de nombre/mismo documento | No une por nombre; conflicto bloquea |
| `TST-CLASS-001` | Clasificación | AFP, entidad pública, `SI`, fondo ausente y evidencia insuficiente | Permanece `DESCONOCIDO` + revisión sin regla aprobada |
| `TST-AUDIT-001` | Trazabilidad | Recalcular desde snapshot/versiones | Mismos valores exactos, incidencias y reglas |
| `TST-EXCEL-001` | Exportación | Comparar backend y libro | Valores y versiones coinciden; no hay constantes/lógica independiente |
| `TST-ARCH-001` | Arquitectura | Importar y ejecutar núcleo sin Dash | Ninguna dependencia de Dash/UI |
| `TST-PPC-001` | PPC | Múltiples años, filas y fechas de corte | Siempre `0.0227`; no existe lookup histórico |

Además se requieren casos CETIL anonimizados de diversas entidades y estructuras, PDFs escaneados,
cifrados, corruptos, vacíos y con tablas rotas; datasets IPC reales y ambiguos; recálculo externo de
libros; y un oráculo aprobado para cada cambio que se aparte de la línea base.

## V. Decisiones todavía pendientes

1. Convención de días aplicable, inclusión de extremos y tratamiento de febrero/fin de mes.
2. Relación entre días declarados en CETIL, días derivados y umbral de discrepancia significativa.
3. Fórmula jurídica del IPC inicial y tratamiento sustantivo de años incompletos.
4. Mes exacto de IPC final, fecha de publicación/disponibilidad y regla de selección al corte.
5. Resolución de duplicados mensuales IPC conflictivos.
6. Conceptos y método jurídico del IBL, meses parciales, variaciones, ceros, empates y atípicos.
7. Fórmula definitiva del SBC, ponderación, unidad y tratamiento de cambios salariales reales.
8. Validez del divisor mensual/semanal `4.345` para el motor objetivo.
9. Política de precisión configurada, puntos de cuantización, escala y modo de redondeo final.
10. Evidencia suficiente y reglas jurídicas para cada clasificación de tiempo.
11. Régimen, AFP, traslados, entidad responsable y reparto, si aplica.
12. Reglas de precedencia entre CETIL complementarios o actualizados.
13. Reglas jurídicas del motor de decisión, incluidas las de bono y 150 semanas, en una fase separada.
14. Fuente autorizada, aprobador y gobernanza de cada `legal_rules_version`.
15. Política aprobada de persistencia, retención y acceso a documentos y evidencia con PII.

Ninguna de estas decisiones pendientes se resuelve copiando el comportamiento legado. PPC no forma
parte de esta lista: está cerrado por `DEC-PPC-001` y no se reabre en esta fase.
