@echo off
setlocal
cd /d "%~dp0"
if exist "convertir_a_markdown.bat" (
    call "convertir_a_markdown.bat" %*
) else if exist "..\convertir_a_markdown.bat" (
    call "..\convertir_a_markdown.bat" %*
) else (
    echo [ERROR] No se encontro convertir_a_markdown.bat
    pause
)
