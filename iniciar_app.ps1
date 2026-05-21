$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$host.UI.RawUI.WindowTitle = "AppIndemnizaciones - Inicio Rapido"

Write-Host "========================================"
Write-Host "  AppIndemnizaciones"
Write-Host "  Iniciando aplicacion..."
Write-Host "========================================"
Write-Host ""

try {
    $pythonCommand = Get-Command python -ErrorAction Stop
} catch {
    Write-Host "ERROR: No se encontro Python en el PATH." -ForegroundColor Red
    Write-Host "Instale Python 3.11+ y marque la opcion 'Add python.exe to PATH'."
    Read-Host "Presione Enter para salir"
    exit 1
}

$activateScript = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Host "No se encontro entorno virtual .venv"
    Write-Host "Creando entorno virtual..."
    python -m venv .venv

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: No se pudo crear el entorno virtual." -ForegroundColor Red
        Write-Host "Verifique que Python este instalado y agregado al PATH."
        Read-Host "Presione Enter para salir"
        exit 1
    }
}

Write-Host "Activando entorno virtual..."
try {
    & $activateScript
} catch {
    Write-Host "ERROR: No se pudo activar el entorno virtual." -ForegroundColor Red
    Write-Host "Si PowerShell bloquea scripts, ejecute:"
    Write-Host "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser"
    Read-Host "Presione Enter para salir"
    exit 1
}

Write-Host ""
Write-Host "Verificando dependencias..."
python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: No se pudo actualizar pip." -ForegroundColor Red
    Read-Host "Presione Enter para salir"
    exit 1
}

if (Test-Path "requirements.txt") {
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: No se pudieron instalar las dependencias de requirements.txt." -ForegroundColor Red
        Read-Host "Presione Enter para salir"
        exit 1
    }
}

if (Test-Path "pyproject.toml") {
    python -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: No se pudo instalar el proyecto en modo editable." -ForegroundColor Red
        Read-Host "Presione Enter para salir"
        exit 1
    }
}

Write-Host ""
Write-Host "Abriendo navegador..."
Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8050/'`""

Write-Host ""
Write-Host "Iniciando servidor Dash..."
Write-Host "Si desea cerrar la app, presione CTRL + C en esta ventana."
Write-Host ""

python app.py

Write-Host ""
Write-Host "La aplicacion se ha detenido."
Read-Host "Presione Enter para salir"
