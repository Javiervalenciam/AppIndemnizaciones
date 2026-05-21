@echo off
setlocal
title AppIndemnizaciones - Inicio Rapido

cd /d "%~dp0"

echo ========================================
echo   AppIndemnizaciones
echo   Iniciando aplicacion...
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: No se encontro Python en el PATH.
    echo Instale Python 3.11+ y marque la opcion "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo No se encontro entorno virtual .venv
    echo Creando entorno virtual...
    python -m venv .venv

    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual.
        echo Verifique que Python este instalado y agregado al PATH.
        pause
        exit /b 1
    )
)

echo Activando entorno virtual...
call ".venv\Scripts\activate.bat"

if errorlevel 1 (
    echo ERROR: No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

echo.
echo Verificando dependencias...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: No se pudo actualizar pip.
    pause
    exit /b 1
)

if exist "requirements.txt" (
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: No se pudieron instalar las dependencias de requirements.txt.
        pause
        exit /b 1
    )
)

if exist "pyproject.toml" (
    python -m pip install -e ".[dev]"
    if errorlevel 1 (
        echo ERROR: No se pudo instalar el proyecto en modo editable.
        pause
        exit /b 1
    )
)

echo.
echo Abriendo navegador...
start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8050/'"

echo.
echo Iniciando servidor Dash...
echo Si desea cerrar la app, presione CTRL + C en esta ventana.
echo.

python app.py

echo.
echo La aplicacion se ha detenido.
pause
