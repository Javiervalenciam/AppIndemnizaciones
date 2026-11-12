# Lanzador de AppIndemnizaciones (compatible con Windows PowerShell 5.1 y PowerShell 7).
# - Usa el Python del entorno .venv directamente (sin "activate").
# - Solo instala dependencias cuando cambia requirements.txt / pyproject.toml.
# - Si la app ya esta corriendo, solo abre el navegador.
# - Abre el navegador cuando el servidor responde (no con una espera fija).
param(
    [switch]$NoBrowser,
    [switch]$ForceInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$Host.UI.RawUI.WindowTitle = "AppIndemnizaciones"

$port = 8050
$url = "http://127.0.0.1:$port/"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$stamp = Join-Path $root ".venv\.deps-stamp"

function Test-PortOpen([int]$p) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", $p, $null, $null)
        return ($async.AsyncWaitHandle.WaitOne(300) -and $client.Connected)
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Stop-WithMessage([string]$message) {
    Write-Host ""
    Write-Host "ERROR: $message" -ForegroundColor Red
    exit 1
}

# 1) Si ya esta corriendo, solo abrir el navegador.
if (Test-PortOpen $port) {
    Write-Host "AppIndemnizaciones ya esta en ejecucion. Abriendo $url"
    if (-not $NoBrowser) { Start-Process $url }
    exit 0
}

# 2) Entorno virtual.
if (-not (Test-Path $venvPython)) {
    Write-Host "Creando entorno virtual (solo la primera vez)..."
    $bootstrap = Get-Command py -ErrorAction SilentlyContinue
    if ($bootstrap) {
        & py -3 -m venv .venv
    } else {
        $bootstrap = Get-Command python -ErrorAction SilentlyContinue
        if (-not $bootstrap) {
            Stop-WithMessage "No se encontro Python. Instale Python 3.11+ y marque 'Add python.exe to PATH'."
        }
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Stop-WithMessage "No se pudo crear el entorno virtual .venv."
    }
    if (Test-Path $stamp) { Remove-Item $stamp -Force }
}

# 3) Dependencias: solo si cambiaron los archivos de requisitos (tamano + fecha).
$hashInput = ""
foreach ($file in @("requirements.txt", "pyproject.toml")) {
    if (Test-Path $file) {
        $info = Get-Item $file
        $hashInput += "$file|$($info.Length)|$($info.LastWriteTimeUtc.Ticks);"
    }
}
$currentStamp = $hashInput
$savedStamp = ""
if (Test-Path $stamp) { $savedStamp = (Get-Content $stamp -Raw).Trim() }

if ($ForceInstall -or $currentStamp -ne $savedStamp) {
    Write-Host "Instalando dependencias (solo cuando cambian)..."
    if (Test-Path "requirements.txt") {
        & $venvPython -m pip install --disable-pip-version-check -q -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Stop-WithMessage "No se pudieron instalar las dependencias." }
    }
    Set-Content -Path $stamp -Value $currentStamp -Encoding ascii
}

# 4) Arrancar el servidor y abrir el navegador cuando responda.
Write-Host "========================================"
Write-Host "  AppIndemnizaciones - $url"
Write-Host "  Cierre esta ventana (o CTRL+C) para detener la app."
Write-Host "========================================"

$server = Start-Process -FilePath $venvPython -ArgumentList "app.py" -NoNewWindow -PassThru

$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    if ($server.HasExited) { break }
    if (Test-PortOpen $port) { $ready = $true; break }
    Start-Sleep -Milliseconds 250
}

if ($ready) {
    if (-not $NoBrowser) { Start-Process $url }
} elseif ($server.HasExited) {
    Stop-WithMessage "El servidor se detuvo al iniciar (codigo $($server.ExitCode)). Revise los mensajes de arriba."
} else {
    Write-Host "El servidor tarda en responder; abra $url manualmente." -ForegroundColor Yellow
}

$server.WaitForExit()
exit $server.ExitCode
