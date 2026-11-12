@echo off
rem Lanzador de AppIndemnizaciones. Toda la logica esta en iniciar_app.ps1.
title AppIndemnizaciones
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar_app.ps1" %*
if errorlevel 1 pause
