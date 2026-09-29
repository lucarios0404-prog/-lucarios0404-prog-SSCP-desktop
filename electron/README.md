# SSCP Desktop - Edición Electron

Versión de escritorio nativa basada en **Electron** para el **Sistema de Seguimiento para Consultas de Pacientes (SSCP)**.

---

## 🌟 Características de esta versión

- **Shell de Escritorio Nativa**: Utiliza el motor Chromium optimizado de Electron v44 con aceleración por hardware.
- **Splash Screen Clínico**: Pantalla de carga profesional con animación ECG y verificación de servicios en tiempo real.
- **Orquestación Automática**: Electron detecta puertos disponibles, inicializa el backend Python (FastAPI/Uvicorn) en segundo plano y monitorea su salud.
- **Entorno de Datos Seguro / Aislado**:
  - Por defecto, la base de datos se clona en `./data/sscp.db` al primer inicio.
  - Esto garantiza que cualquier prueba, modificación o consulta en esta versión Electron **no altere los datos de producción** de la versión original de `sscp-desktop`.
- **Cierre Limpio (Zero-Zombies)**: Al cerrar la ventana o salir de la aplicación, el proceso de Python en segundo plano se finaliza automáticamente sin dejar procesos huérfanos en el Administrador de Tareas.
- **Menú de Aplicación Nativo de Windows**:
  - Atajos rápidos: `CmdOrCtrl+H` (Dashboard), `CmdOrCtrl+Alt+P` (Nuevo Paciente), `CmdOrCtrl+Alt+A` (Nueva Cita).
  - Impresión directa nativa: `CmdOrCtrl+P`.
  - Recarga con `F5` / `Ctrl+F5` y pantalla completa con `F11`.
  - Herramientas de desarrollador con `Ctrl+Shift+I` para inspección rápida de estilos e interfaces.
- **Bandeja del Sistema (System Tray)**: Icono en la barra de tareas de Windows para abrir, minimizar o salir rápidamente.

---

## 🚀 Cómo Iniciar la Aplicación

### Opción 1: Un solo clic (Recomendado)
Haz doble clic sobre:
```bat
start.bat
```

### Opción 2: Desde la terminal
```bash
npm start
```

---

## ⚙️ Configuración (`config/config.json`)

Puedes personalizar el comportamiento en `config/config.json`:

```json
{
  "appName": "SSCP Desktop (Electron Edition)",
  "backendDir": "c:/Users/Ecommerce/Desktop/Sistema de Seguimiento para Consultas de Pacientes - SSCP/sscp-desktop",
  "pythonExe": "c:/Users/Ecommerce/Desktop/Sistema de Seguimiento para Consultas de Pacientes - SSCP/sscp-desktop/venv/Scripts/python.exe",
  "defaultPort": 8080,
  "useIsolatedData": true,
  "isolatedDataDir": "./data",
  "window": {
    "width": 1360,
    "height": 860,
    "minWidth": 1024,
    "minHeight": 700
  }
}
```

* Si cambias `"useIsolatedData": false`, la aplicación se conectará directamente a la base de datos viva original.
* Si el puerto 8080 está ocupado por otra instancia, Electron encontrará automáticamente el siguiente puerto libre (8081, 8082, etc.).

---

## 📁 Estructura del Proyecto

```text
electron version/
├── config/
│   └── config.json           # Ajustes de backend, puertos y ventana
├── data/
│   ├── sscp.db               # Base de datos SQLite aislada de prueba
│   └── backend.log           # Registro de actividad del servidor
├── src/
│   ├── assets/               # Icono de la aplicación (.ico)
│   ├── main/
│   │   ├── main.js           # Proceso principal de Electron y ciclo de vida
│   │   ├── menu.js           # Menú nativo con atajos de teclado
│   │   └── server-manager.js # Gestor y monitor del backend FastAPI
│   ├── preload/
│   │   └── preload.js        # Context bridge e IPC seguro
│   └── splash/
│       └── splash.html       # Splash screen médico animado
├── package.json
├── sscp-electron-plan.md     # Documento del plan ejecutado
├── start.bat                 # Lanzador de un clic para Windows
└── README.md
```
