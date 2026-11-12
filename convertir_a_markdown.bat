@echo off
setlocal enabledelayedexpansion
title Convertidor a Markdown - Microsoft MarkItDown

cd /d "%~dp0"

echo =======================================================================
echo     CONVERTIDOR DE DOCUMENTOS A MARKDOWN - MICROSOFT MARKITDOWN
echo            Optimizador de Archivos para Ahorro de Tokens en IA
echo =======================================================================
echo.

:: 1. Detectar script convertir.py
set "SCRIPT_PY="
if exist "%~dp0convertir.py" (
    set "SCRIPT_PY=%~dp0convertir.py"
) else if exist "%~dp0conversor_markdown\convertir.py" (
    set "SCRIPT_PY=%~dp0conversor_markdown\convertir.py"
)

if "!SCRIPT_PY!"=="" (
    echo [ERROR] No se encontro el archivo convertir.py en esta carpeta.
    echo.
    pause
    exit /b 1
)

:: 2. Detectar python.exe
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
)

if "!PYTHON_EXE!"=="" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] No se encontro Python instalado en el sistema.
        echo Por favor instala Python 3.11 o superior y marca Add Python to PATH.
        echo.
        pause
        exit /b 1
    )
    echo [INFO] Creando entorno virtual .venv...
    python -m venv "%~dp0.venv"
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)

:: 3. Verificar dependencias
"!PYTHON_EXE!" -c "import markitdown, mammoth, pptx, openpyxl, pdfplumber" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Instalando librerias requeridas para conversion de documentos...
    "!PYTHON_EXE!" -m pip install markitdown mammoth lxml python-docx python-pptx openpyxl pandas pdfplumber xlrd olefile
    if errorlevel 1 (
        echo [ERROR] No se pudieron instalar las dependencias automaticamente.
        echo.
        pause
        exit /b 1
    )
)

:: 4. Modo Arrastrar y Soltar
if not "%~1"=="" (
    echo [MODO ARRASTRAR Y SOLTAR] Procesando archivos recibidos...
    echo.
    "!PYTHON_EXE!" "!SCRIPT_PY!" %*
    echo.
    echo -----------------------------------------------------------------------
    echo Proceso completado. Revisa tus archivos en la carpeta salida.
    echo -----------------------------------------------------------------------
    pause
    exit /b 0
)

:: 5. Modo Menu Interactivo
"!PYTHON_EXE!" "!SCRIPT_PY!"

if errorlevel 1 (
    echo.
    echo [AVISO] Ocurrio un error al ejecutar el convertidor.
)

pause
exit /b 0
