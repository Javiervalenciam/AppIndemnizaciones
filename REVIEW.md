# REVIEW.md

## Checklist de revisión técnica

### Arquitectura

- [ ] `app.py` solo inicializa Dash.
- [ ] Los callbacks viven en `src/app_indemnizaciones/ui/callbacks.py`.
- [ ] La lógica de IPC vive en `services/ipc_loader.py`.
- [ ] La lógica matemática vive en `services/liquidacion_service.py`.
- [ ] Los modelos viven en `domain/models.py`.

### IPC

- [ ] Soporta Excel Banco República con hoja `Datos`.
- [ ] Soporta CSV/Excel con `Año(aaaa)-Mes(mm)` e `Índice`.
- [ ] Ignora filas de formato, notas o valores vacíos.
- [ ] Detecta IPC actual como último registro válido si no se define fecha de liquidación.
- [ ] Lanza error claro si falta el mes solicitado.

### Liquidación

- [ ] Usa días comerciales 360 por defecto.
- [ ] Permite cambiar a días calendario si se requiere.
- [ ] Conserva PPC = 0.0227 configurable.
- [ ] Redondea solo para presentación/exportación, no en el cálculo intermedio.

### Seguridad y privacidad

- [ ] No se guardan datos personales en repositorio.
- [ ] No se imprimen documentos ni cédulas en logs.
- [ ] Archivos de usuario quedan fuera de Git.
