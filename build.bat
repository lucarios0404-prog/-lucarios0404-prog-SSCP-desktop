@echo off
chcp 65001 >nul
title Compilador Integral SSCP Desktop (Windows x64)
echo ========================================================
echo   SSCP Desktop - Pipeline Integral de Compilación
echo ========================================================
echo.

call venv\Scripts\activate.bat

echo [1/3] Compilando backend FastAPI con PyInstaller...
python build_exe.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo al compilar backend PyInstaller.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Empaquetando runtime Electron y recursos...
python scripts\build_electron_package.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo al empaquetar shell Electron.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Generando instalador ejecutable oficial (NSIS)...
call build_installer.bat
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo al generar el instalador NSIS.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo   [EXITO] Compilacion completada satisfactoriamente.
echo ========================================================
echo.
pause
