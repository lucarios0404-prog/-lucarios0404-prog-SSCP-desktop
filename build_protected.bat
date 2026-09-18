@echo off
setlocal enabledelayedexpansion

echo ================================================================
echo   SSCP Desktop - Build Protegido con PyArmor + PyInstaller
echo ================================================================
echo.

REM === PASO 0: Activar entorno virtual si existe ===
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM === PASO 1: Verificar dependencias ===
echo [1/5] Verificando dependencias...
pip show pyarmor >nul 2>&1 || pip install pyarmor
pip show wmi >nul 2>&1 || pip install wmi
pip show cryptography >nul 2>&1 || pip install cryptography
echo    OK

REM === PASO 2: Limpiar build anterior ===
echo [2/5] Limpiando build anterior...
if exist "app_obfuscated" rmdir /s /q "app_obfuscated"
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo    OK

REM === PASO 3: Ofuscar codigo con PyArmor ===
echo [3/5] Ofuscando codigo fuente con PyArmor...
pyarmor gen --output app_obfuscated app/
if errorlevel 1 (
    echo    ERROR: PyArmor fallo. Abortando.
    exit /b 1
)
echo    OK

REM === PASO 4: Compilar con PyInstaller ===
echo [4/5] Compilando ejecutable con PyInstaller...
pyinstaller --noconfirm sscp_desktop.spec
if errorlevel 1 (
    echo    ERROR: PyInstaller fallo. Abortando.
    exit /b 1
)
echo    OK

REM === PASO 5: Generar instalador NSIS ===
echo [5/5] Generando instalador NSIS...
if exist "tools\nsis-3.10\makensis.exe" (
    tools\nsis-3.10\makensis.exe installer.nsi
    if errorlevel 1 (
        echo    ERROR: NSIS fallo.
        exit /b 1
    )
    echo    OK
) else (
    echo    AVISO: NSIS no encontrado en tools\nsis-3.10\. Saltando paso de instalador.
)

echo.
echo ================================================================
echo   BUILD COMPLETADO
set "FOUND_INSTALLER="
for %%f in (dist\SSCP_Desktop_Setup_v*.exe) do set "FOUND_INSTALLER=%%f"
if defined FOUND_INSTALLER (
    echo   Instalador: !FOUND_INSTALLER!
) else (
    echo   Ejecutable: dist\SSCP-Desktop\SSCP-Desktop.exe
)
echo ================================================================
