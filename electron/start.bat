@echo off
title SSCP Desktop - Electron Launcher
cd /d "%~dp0"
echo ========================================================
echo   Iniciando SSCP Desktop (Edicion Electron)
echo ========================================================
npm start
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo [ERROR] Hubo un problema al iniciar la aplicacion.
  pause
)
