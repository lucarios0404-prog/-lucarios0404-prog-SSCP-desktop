; ==============================================================================
; SSCP Desktop - Script de Instalador NSIS (Nullsoft Scriptable Install System)
; Genera el instalador oficial autocontenido para Windows 10/11 x64
; ==============================================================================

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"

; Definiciones Generales
!define PRODUCT_NAME "SSCP Desktop"
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "1.3.1"
!endif
!define PRODUCT_PUBLISHER "SSCP Medical Systems"
!define PRODUCT_WEB_SITE "https://sscp.laxarusdevs.com"
!define PRODUCT_EXE "SSCP-Desktop.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\SSCP_Desktop_Setup_v${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\SSCP Desktop"
InstallDirRegKey HKLM "${PRODUCT_UNINST_KEY}" "UninstallString"
RequestExecutionLevel admin

; Interfaz Moderna (MUI2)
!define MUI_ABORTWARNING
!define MUI_ICON "static\app_icon.ico"
!define MUI_UNICON "static\app_icon.ico"

; Páginas del Asistente de Instalación
!define MUI_WELCOMEPAGE_TITLE "Bienvenido al Instalador de ${PRODUCT_NAME} v${PRODUCT_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instalará o actualizará ${PRODUCT_NAME} en su equipo.$\r$\n$\r$\nPara actualizar no es necesario desinstalar la versión anterior; sus historias clínicas, configuraciones de consultorio, márgenes calibrados y licencias se mantendrán intactos de forma 100% segura.$\r$\n$\r$\nHaga clic en Siguiente para continuar."
!insertmacro MUI_PAGE_WELCOME

; Pagina EULA (Acuerdo de Licencia de Uso)
!insertmacro MUI_PAGE_LICENSE "EULA.txt"

!insertmacro MUI_PAGE_DIRECTORY

!insertmacro MUI_PAGE_INSTFILES

Function LaunchApp
  ExecShell "" "$INSTDIR\${PRODUCT_EXE}"
FunctionEnd

!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "Ejecutar ${PRODUCT_NAME} ahora"
!insertmacro MUI_PAGE_FINISH

; Páginas del Desinstalador
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; Idioma
!insertmacro MUI_LANGUAGE "Spanish"

; Sección de Instalación Principal
Section "MainSection" SEC01
  ; Cerrar cualquier instancia previa de la aplicación para asegurar sobreescritura limpia
  nsExec::Exec 'taskkill /F /IM SSCP-Desktop.exe /T'
  Sleep 500

  SetOutPath "$INSTDIR"
  SetOverwrite on

  ; Copiar todos los archivos de la distribución Electron (Shell Chromium + App + Backend Python)
  File /r "dist\SSCP-Desktop-Electron\*.*"

  ; Copiar icono oficial garantizado para accesos directos
  File "/oname=app_icon.ico" "static\app_icon.ico"

  ; Crear Accesos Directos con icono oficial explícito
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\app_icon.ico" 0
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Desinstalar ${PRODUCT_NAME}.lnk" "$INSTDIR\uninst.exe" "" "$INSTDIR\app_icon.ico" 0
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\app_icon.ico" 0

  ; Escribir desinstalador
  WriteUninstaller "$INSTDIR\uninst.exe"

  ; Registrar en el Panel de Control (Agregar o Quitar Programas)
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\app_icon.ico"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"

  ; Habilitar regla de Firewall para permitir conexión de Tablets y Estaciones en red local (puerto 8080)
  nsExec::Exec 'netsh advfirewall firewall add rule name="SSCP Desktop Server (Port 8080)" dir=in action=allow protocol=TCP localport=8080 profile=any'
SectionEnd

; Sección del Desinstalador
Section Uninstall
  ; Eliminar regla de Firewall
  nsExec::Exec 'netsh advfirewall firewall delete rule name="SSCP Desktop Server (Port 8080)"'

  ; Eliminar accesos directos
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Desinstalar ${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  ; Eliminar archivos de la aplicación
  RMDir /r "$INSTDIR\resources"
  RMDir /r "$INSTDIR\locales"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\*.*"

  ; Los datos clínicos persisten de forma segura en %APPDATA%\SSCP Desktop\data para no perder historiales
  Delete "$INSTDIR\uninst.exe"
  RMDir "$INSTDIR"

  ; Limpiar registro de Windows
  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
SectionEnd
