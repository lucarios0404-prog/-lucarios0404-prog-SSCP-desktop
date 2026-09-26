; ==============================================================================
; SSCP Desktop - Script de Instalador NSIS (Nullsoft Scriptable Install System)
; Genera el instalador oficial autocontenido para Windows 10/11 x64
; ==============================================================================

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"

; Definiciones Generales
!define PRODUCT_NAME "SSCP Desktop"
!define PRODUCT_VERSION "1.0.8"
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
!insertmacro MUI_PAGE_WELCOME

; Pagina EULA (Acuerdo de Licencia de Uso)
!insertmacro MUI_PAGE_LICENSE "EULA.txt"

!insertmacro MUI_PAGE_DIRECTORY


!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_EXE}"
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
  SetOutPath "$INSTDIR"
  SetOverwrite try

  ; Copiar todos los archivos binarios generados por PyInstaller
  File /r "dist\SSCP-Desktop\*.*"

  ; Crear directorio local para base de datos SQLite persistente
  CreateDirectory "$INSTDIR\data"

  
  ; Crear Accesos Directos
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Desinstalar ${PRODUCT_NAME}.lnk" "$INSTDIR\uninst.exe" "" "$INSTDIR\uninst.exe" 0
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0

  ; Escribir desinstalador
  WriteUninstaller "$INSTDIR\uninst.exe"

  ; Registrar en el Panel de Control (Agregar o Quitar Programas)
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\${PRODUCT_EXE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd

; Sección del Desinstalador
Section Uninstall
  ; Eliminar accesos directos
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Desinstalar ${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  ; Eliminar archivos de la aplicación
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\*.*"

  ; Conservar la base de datos data\sscp.db para no perder historiales clínicos por accidente
  ; Si se desea eliminar por completo, descomentar la siguiente línea:
  ; RMDir /r "$INSTDIR\data"

  Delete "$INSTDIR\uninst.exe"
  RMDir "$INSTDIR"

  ; Limpiar registro de Windows
  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
SectionEnd

