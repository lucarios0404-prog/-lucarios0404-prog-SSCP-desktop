@echo off
chcp 65001 >nul
echo =======================================================
echo Compilador de Instalador Windows NSIS - SSCP Desktop
echo =======================================================

set MAKENSIS_BIN=
if exist "tools\nsis-3.10\makensis.exe" set MAKENSIS_BIN=tools\nsis-3.10\makensis.exe
if not defined MAKENSIS_BIN if exist "C:\Program Files (x86)\NSIS\makensis.exe" set MAKENSIS_BIN="C:\Program Files (x86)\NSIS\makensis.exe"
if not defined MAKENSIS_BIN where makensis >nul 2>nul && set MAKENSIS_BIN=makensis

if defined MAKENSIS_BIN (
    echo [OK] Compilador NSIS detectado: %MAKENSIS_BIN%
    echo Generando instalador NSIS...
    %MAKENSIS_BIN% installer.nsi
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo =======================================================
        echo [EXITO] Instalador creado en dist\
        dir /b dist\SSCP_Desktop_Setup_v*.exe 2>nul
        echo =======================================================
    ) else (
        echo [ERROR] Error durante la compilacion de NSIS.
    )
) else (
    echo [AVISO] 'makensis' no se encuentra en el sistema.
    echo Descargue NSIS o ejecute tools\nsis-3.10\makensis.exe
)
