# AppIndemnizaciones 🇨🇴

> Aplicación administrativa en **Python + Dash** para apoyar la liquidación de **Indemnización Sustitutiva de Vejez (ISV)** a partir de histórico IPC, certificados CETIL y reglas de cálculo trazables.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-0057B8?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Dash" src="https://img.shields.io/badge/Dash-App-4F46E5?style=for-the-badge&logo=plotly&logoColor=white">
  <img alt="CETIL" src="https://img.shields.io/badge/CETIL-PDF-06B6D4?style=for-the-badge">
  <img alt="Colombia" src="https://img.shields.io/badge/Colombia-ISV-FCD116?style=for-the-badge">
</p>

<p align="center">
  <strong>IPC histórico</strong> · <strong>Extracción CETIL</strong> · <strong>Cuadro anualizado</strong> · <strong>Cálculo trazable</strong> · <strong>Exportación Excel</strong>
</p>

---

## Vista General

**AppIndemnizaciones** centraliza un flujo de liquidación que normalmente se realiza en hojas de cálculo manuales. La aplicación permite cargar el histórico IPC, procesar un certificado CETIL en PDF, revisar la información extraída, anualizar periodos certificados, calcular valores trazables por fila y exportar un Excel de liquidación.

La interfaz está diseñada como una aplicación administrativa moderna con estilo **Liquid Glass / Material-inspired**, tarjetas translúcidas, KPIs, tabla de revisión y resultados claros para auditoría.

---

## Qué Hace La App

| Módulo | Descripción |
| --- | --- |
| **Carga IPC** | Lee archivos Excel/CSV con índices IPC históricos, detecta rango de datos e identifica el IPC actual/final. |
| **Carga CETIL** | Procesa PDF CETIL, extrae datos del empleado, certificado, entidad empleadora, periodos y factores salariales. |
| **Normalización anual** | Convierte periodos certificados en filas por año calendario, respetando fechas reales de inicio y fin. |
| **Revisión manual** | Permite revisar y ajustar fechas, IBL reportado, cargo y entidad antes de calcular. |
| **Motor de cálculo** | Calcula días, semanas, IPC inicial anual, IPC actual, indexación e IBC semanal actualizado. |
| **KPIs de liquidación** | Muestra DÍAS EN TOTAL, SC, PPC, SBC y LIQUIDACIÓN DE APORTES. |
| **Exportación Excel** | Genera archivo `.xlsx` con tabla, KPIs, datos CETIL, datos IPC y fórmulas compatibles con Excel. |

---

## Flujo De Trabajo

```mermaid
flowchart LR
    A["Cargar IPC histórico"] --> B["Cargar PDF CETIL"]
    B --> C["Datos extraídos del CETIL"]
    C --> D["Cuadro de liquidación anual"]
    D --> E["Revisión manual"]
    E --> F["Calcular liquidación"]
    F --> G["KPIs y tabla de resultado"]
    G --> H["Descargar Excel"]
```

---

## Características Principales

- Extracción de datos desde PDF CETIL.
- Identificación de empleado, documento, certificado y entidad empleadora.
- Reconstrucción de factores salariales incluso cuando el bloque se parte entre páginas.
- Anualización de periodos certificados por año calendario.
- Cálculo de IPC inicial como promedio anual.
- Uso del último IPC válido como IPC actual/final.
- Validación previa antes del cálculo.
- Separación entre tabla de revisión y resultados calculados.
- Columnas calculadas bloqueadas para proteger trazabilidad.
- Exportación Excel con nombre basado en documento del trabajador.
- Diseño visual moderno con tipografía Poppins y fondo interactivo.

---

## Fórmulas Clave

La lógica de cálculo se encuentra en servicios de dominio, no en callbacks ni componentes UI.

| Concepto | Fórmula |
| --- | --- |
| Días | `DAYS360(fecha_inicio, fecha_fin)` |
| Semanas | `dias / 7` |
| PPC | `0.0227` |
| IBC actualizado | `IBL reportado * (IPC actual / IPC inicial)` |
| IBC semanal actualizado | `IBC actualizado / 4.345` |
| SBC | Promedio simple de IBC semanal actualizado |
| Liquidación de aportes | `SBC * SC * PPC` |

---

## Interfaz

La app está organizada en secciones claras:

1. **IPC histórico**
   - Carga del archivo IPC.
   - Resumen de registros y rango.
   - IPC actual/final detectado.

2. **Certificado CETIL**
   - Carga del PDF.
   - Limpieza de sesión CETIL.
   - Extracción de periodos y factores salariales.

3. **Datos extraídos del CETIL**
   - Trabajador.
   - Documento.
   - Fecha de nacimiento.
   - Número CETIL.
   - Entidad empleadora.
   - NIT.
   - Advertencias de extracción.

4. **Cuadro de liquidación anual**
   - Año.
   - Fecha desde.
   - Fecha hasta.
   - IBL reportado.
   - Cargo.
   - Entidad.
   - Estado.
   - Errores / advertencias.

5. **Resultado de liquidación**
   - Tabla calculada.
   - KPIs.
   - Botón de descarga Excel.

---

## Estructura Del Proyecto

```text
AppIndemnizaciones/
├── app.py
├── assets/
│   ├── styles.css
│   ├── theme.css
│   └── liquid_background.js
├── src/
│   └── app_indemnizaciones/
│       ├── domain/
│       ├── services/
│       ├── ui/
│       └── utils/
├── tests/
├── requirements.txt
├── pyproject.toml
├── BUILD.md
└── README.md
```

---

## Instalación

### 1. Clonar El Repositorio

```bash
git clone https://github.com/Davincce/AppIndemnizaciones.git
cd AppIndemnizaciones
```

### 2. Crear Entorno Virtual

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows CMD:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar Dependencias

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Ejecución

```bash
python app.py
```

Abrir en el navegador:

```text
http://127.0.0.1:8050
```

También puedes usar los scripts incluidos:

```powershell
.\iniciar_app.ps1
```

```bat
iniciar_app.bat
```

---

## Verificación Del Proyecto

Ejecutar antes de publicar cambios:

```bash
python -m pytest -q
python -m ruff check .
python -m compileall src app.py
```

Estado esperado:

- Tests pasando.
- Ruff sin errores.
- Compilación Python correcta.

---

## Exportación Excel

El Excel generado incluye:

- Datos del trabajador y certificado CETIL.
- Datos de entidad empleadora.
- Datos IPC usados.
- Tabla anualizada de liquidación.
- Fórmulas reales en celdas calculadas.
- KPIs finales.
- Nombre de archivo con documento del trabajador cuando está disponible.

Ejemplo:

```text
Liquidacion_ISV_88152324.xlsx
```

---

## Principios Técnicos

- Arquitectura modular.
- Separación entre dominio, servicios, UI y utilidades.
- Cálculos fuera de callbacks Dash.
- Extracción documental aislada en servicios.
- Datos CETIL sujetos a revisión manual.
- Validaciones antes del cálculo.
- Trazabilidad por fila.
- Tests unitarios para IPC, CETIL, normalización, cálculo, UI y exportación.

---

## Tecnologías

| Tecnología | Uso |
| --- | --- |
| Python | Backend y lógica principal |
| Dash | Aplicación web administrativa |
| dash-bootstrap-components | Componentes UI |
| pandas | Procesamiento tabular |
| pdfplumber / PyMuPDF | Extracción PDF |
| openpyxl / xlsxwriter | Exportación Excel |
| pytest | Pruebas |
| ruff | Linting |

---

## Créditos De Desarrollo

Esta aplicación se desarrolló con el apoyo de **Codex de OpenAI** y los modelos
**GPT-5.6 Sol y GPT-5.6 Terra**. Esta atribución reconoce las herramientas que
acompañaron el proceso de desarrollo; las fórmulas, validaciones y resultados
de la liquidación continúan siendo responsabilidad de la aplicación y de la
revisión humana correspondiente.

---

## Seguridad Y Buenas Prácticas

El repositorio ignora artefactos locales y temporales:

- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`
- `*.pyc`
- `*.log`
- `node_modules/`
- `dist/`
- `build/`
- archivos temporales

No se deben versionar certificados reales, archivos personales, claves, tokens, PDFs privados ni documentos con datos sensibles.

---

## Roadmap Sugerido

- Agregar capturas de pantalla oficiales.
- Añadir modo oscuro institucional.
- Incorporar pruebas visuales automatizadas.
- Mejorar soporte para variaciones complejas de CETIL.
- Agregar empaquetado para despliegue interno.
- Crear manual de usuario final.

---

## Autor

**Javier Andrés Valencia Moreno**  
CEO · Colombia ® 🇨🇴

---

## Licencia

Proyecto privado/institucional. Definir licencia formal antes de distribución pública o uso por terceros.
