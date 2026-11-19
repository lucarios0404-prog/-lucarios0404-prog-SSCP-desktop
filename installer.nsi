; ==============================================================================
; SSCP Desktop - Script de Instalador NSIS (Nullsoft Scriptable Install System)
; Genera el instalador oficial autocontenido para Windows 10/11 x64
; ==============================================================================

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"

; Variables para página de configuración Supabase durante la instalación
Var SupaDialog
Var SupaCtlToken
Var SupaCtlClinic
Var SupaCtlUrl
Var SupaCtlAnon
Var SupaToken
Var SupaClinic
Var SupaUrl
Var SupaKey
Var SupaFileHandle
Var SupaLine1
Var SupaLine2
Var SupaLine3

; Definiciones Generales
!define PRODUCT_NAME "SSCP Desktop"
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "1.8.7-supabase"
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

ReserveFile "dist\sscp_supa_init.exe"

; Interfaces Modernas (MUI2)
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

; Página personalizada: Conexión en la Nube Supabase del Doctor
Page custom SupabasePageCreate SupabasePageLeave

!insertmacro MUI_PAGE_INSTFILES

Function LaunchApp
  Exec '"$WINDIR\explorer.exe" "$INSTDIR\${PRODUCT_EXE}"'
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

Function SupabasePageCreate
  !insertmacro MUI_HEADER_TEXT "Nube Supabase del Doctor" "Ingresa la Key de tu cuenta Supabase para configurar proyecto, tablas y Keep-Alive al instalar."
  nsDialogs::Create 1018
  Pop $SupaDialog
  ${If} $SupaDialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "El instalador creara las tablas de Supabase y activara la sincronizacion 100% en la nube. Si actualizas una PC vieja, tus pacientes se conservan intactos."
  Pop $0

  ${NSD_CreateLabel} 0 30u 100% 12u "Key de tu cuenta Supabase (sbp_...) — Recomendado (configura todo solo):"
  Pop $0
  ${NSD_CreateText} 0 43u 100% 13u "$SupaToken"
  Pop $SupaCtlToken

  ${NSD_CreateLabel} 0 62u 100% 12u "ID o Nombre corto del Doctor (opcional, ej: dr_perez):"
  Pop $0
  ${NSD_CreateText} 0 75u 100% 13u "$SupaClinic"
  Pop $SupaCtlClinic

  ${NSD_CreateLabel} 0 94u 100% 12u "Opcional manual (solo si no usas sbp_...) — Project URL:"
  Pop $0
  ${NSD_CreateText} 0 107u 49% 13u "$SupaUrl"
  Pop $SupaCtlUrl

  ${NSD_CreateText} 51% 107u 49% 13u "$SupaKey"
  Pop $SupaCtlAnon

  ${NSD_CreateLabel} 0 124u 100% 16u "(Puedes dejarlo vacio si deseas configurarlo despues dentro de SSCP Desktop.)"
  Pop $0

  nsDialogs::Show
FunctionEnd

Function SupabasePageLeave
  ${NSD_GetText} $SupaCtlToken $SupaToken
  ${NSD_GetText} $SupaCtlClinic $SupaClinic
  ${NSD_GetText} $SupaCtlUrl $SupaUrl
  ${NSD_GetText} $SupaCtlAnon $SupaKey

  ; Cerrar instancias previas de SSCP ANTES de acceder a SQLite o copiar archivos
  nsExec::Exec 'taskkill /F /IM SSCP-Desktop.exe /T'
  nsExec::Exec 'taskkill /F /IM "SSCP Desktop.exe" /T'
  nsExec::Exec 'taskkill /F /IM electron.exe /T'
  Sleep 800

  ; Ejecutar y verificar Supabase ANTES de iniciar la copia de archivos en la PC
  ${If} $SupaToken != ""
  ${OrIf} $SupaUrl != ""
    InitPluginsDir
    File "/oname=$PLUGINSDIR\sscp_supa_init.exe" "dist\sscp_supa_init.exe"
    FileOpen $SupaFileHandle "$PLUGINSDIR\supa_install.txt" w
    FileWrite $SupaFileHandle "access_token=$SupaToken$\r$\n"
    FileWrite $SupaFileHandle "clinic_id=$SupaClinic$\r$\n"
    FileWrite $SupaFileHandle "supabase_url=$SupaUrl$\r$\n"
    FileWrite $SupaFileHandle "supabase_anon_key=$SupaKey$\r$\n"
    FileClose $SupaFileHandle

    nsExec::Exec '"$PLUGINSDIR\sscp_supa_init.exe" --provision-supabase-file "$PLUGINSDIR\supa_install.txt"'
    Pop $0

    StrCpy $SupaLine1 ""
    StrCpy $SupaLine2 ""
    StrCpy $SupaLine3 ""
    ${If} ${FileExists} "$PLUGINSDIR\supa_install.txt.status.txt"
      FileOpen $SupaFileHandle "$PLUGINSDIR\supa_install.txt.status.txt" r
      FileRead $SupaFileHandle $SupaLine1
      FileRead $SupaFileHandle $SupaLine2
      FileRead $SupaFileHandle $SupaLine3
      FileClose $SupaFileHandle
    ${EndIf}
    Delete "$PLUGINSDIR\supa_install.txt"
    Delete "$PLUGINSDIR\supa_install.txt.status.txt"

    ${If} $0 != 0
      MessageBox MB_YESNO|MB_ICONSTOP "Error conectando o configurando Supabase:$\r$\n$\r$\n$SupaLine1$\r$\n¿Deseas corregir tus datos de Supabase antes de instalar en la PC?$\r$\n(Si pulsas NO, continuara instalando SSCP Desktop para configurarlo luego.)" IDNO skip_supa_abort
      Abort
      skip_supa_abort:
    ${Else}
      MessageBox MB_OK|MB_ICONINFORMATION "Nube Supabase aprobada y configurada!$\r$\n$\r$\n$SupaLine1$SupaLine2$SupaLine3$\r$\nPresiona Aceptar para comenzar la instalacion en esta PC."
    ${EndIf}
  ${EndIf}
FunctionEnd

; Sección de Instalación Principal
Section "MainSection" SEC01
  ; Cerrar cualquier instancia previa de la aplicación para asegurar sobreescritura limpia
  nsExec::Exec 'taskkill /F /IM SSCP-Desktop.exe /T'
  nsExec::Exec 'taskkill /F /IM "SSCP Desktop.exe" /T'
  nsExec::Exec 'taskkill /F /IM electron.exe /T'
  Sleep 1000

  SetOutPath "$INSTDIR"
  SetOverwrite on

  ; Copiar todos los archivos de la distribución Electron + Backend (-supabase)
  File /r "dist\SSCP-Desktop-v${PRODUCT_VERSION}\*.*"

  ; Directorio de datos de usuario limpio (conserva sscp.db si ya existía)
  SetShellVarContext current
  CreateDirectory "$LOCALAPPDATA\SSCP\data"
  SetShellVarContext all

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
SectionEnd

; Sección del Desinstalador
Section Uninstall

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
