# Crea el acceso directo "AppIndemnizaciones" (con icono) en el Escritorio y en el
# menu Inicio. Ejecutar una vez:  powershell -ExecutionPolicy Bypass -File crear_acceso_directo.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$icon = Join-Path $root "assets\favicon.ico"
$bat = Join-Path $root "iniciar_app.bat"

if (-not (Test-Path $icon)) {
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    & $venvPython (Join-Path $root "scripts\build_icon.py")
}

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "")
)
foreach ($folder in $targets) {
    if (-not (Test-Path $folder)) { continue }
    $path = Join-Path $folder "AppIndemnizaciones.lnk"
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $bat
    $link.WorkingDirectory = $root
    $link.IconLocation = "$icon,0"
    $link.Description = "Liquidacion de indemnizacion sustitutiva de vejez (ISV)"
    $link.WindowStyle = 7   # consola minimizada: solo se ve el navegador
    $link.Save()
    Write-Host "Acceso directo creado: $path"
}
