@echo off
chcp 65001 >nul
echo =======================================================
echo Compilador de Instalador Windows NSIS - SSCP Desktop
echo =======================================================

where makensis >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Compilador NSIS detectado en PATH.
    echo Generando dist\SSCP_Desktop_Setup_v1.0.0.exe...
    makensis installer.nsi
    if %ERRORLEVEL% EQU 0 (
        echo [EXITO] Instalador creado en dist\SSCP_Desktop_Setup_v1.0.0.exe
    ) else (
        echo [ERROR] Error durante la compilacion de NSIS.
    )
) else (
    echo [AVISO] 'makensis' no se encuentra en el PATH del sistema.
    echo Para generar el instalador .exe ejecutable de instalacion:
    echo 1. Descargue NSIS desde https://nsis.sourceforge.io/Download
    echo 2. Ejecute: makensis.exe installer.nsi
    echo.
    echo Nota: El paquete portable ejecutable ya esta 100%% compilado en:
    echo       dist\SSCP-Desktop\SSCP-Desktop.exe
)
