# Plan: SSCP Desktop en Electron (Versión Independiente)

## 📌 Objetivo
Crear una versión de escritorio basada en **Electron** para el **Sistema de Seguimiento para Consultas de Pacientes (SSCP)** dentro del directorio `electron version`, manteniéndolo como un proyecto 100% independiente del original para evaluar su apariencia, fluidez, integración nativa y rendimiento.

---

## 🔍 Análisis de la Infraestructura Existente
En `c:\Users\Ecommerce\Desktop\Sistema de Seguimiento para Consultas de Pacientes - SSCP`:
- **`sscp-desktop`**: Aplicación basada en Python 3.10+ / FastAPI / SQLite (`data/`) / plantillas Jinja2 / PyWebView.
- **`sscp`**: Aplicación web central (Laravel / PHP / Filament / Vite).
- **Runtimes del sistema disponibles**:
  - Node.js: `v24.15.0`
  - npm: `11.12.1`
  - Python: `3.11.15`

---

## 🏗️ Opciones de Arquitectura

### Opción 1 (Recomendada): Electron Shell + Orquestación de Backend SSCP (Híbrida)
* **Cómo funciona**: Electron gestiona el ciclo de vida de la aplicación de escritorio, menús, bandeja del sistema (tray), aceleración gráfica de Chromium e impresión nativa. En el inicio, Electron orquesta el backend existente de SSCP (FastAPI + SQLite) en segundo plano o se conecta al servicio local.
* **Ventajas**:
  - Conserva el 100% de los módulos médicos existentes (pacientes, consultas, recetas, PDF, inventario, firmas).
  - Permite comparar de inmediato la experiencia de usuario y rendimiento entre PyWebView y Electron sin reescribir lógica de negocio.
  - Cero riesgo para la base de datos original (se puede usar una copia de prueba).

### Opción 2: Electron SPA (Vite + React / TypeScript) consumiendo la API de SSCP
* **Cómo funciona**: Se crea una interfaz de usuario completamente nueva en React/Tailwind dentro de Electron que consume los endpoints REST/JSON existentes de SSCP (`mobile_api.py` / routers).
* **Ventajas**: Interfaz moderna tipo Single Page Application, pero requiere maquetar y conectar cada módulo médico desde cero.

---

## 📋 Fases del Plan de Implementación (Pendiente de Aprobación "OKI")

### Fase 1: Inicialización del Proyecto Electron
- Inicializar `package.json` en `c:\Users\Ecommerce\Desktop\electron version`.
- Instalar dependencias base: `electron`, `electron-builder` (para futuros instaladores `.exe`), y utilidades de desarrollo (`concurrently`, `wait-on`).
- Configurar estructura de carpetas:
  ```text
  electron version/
  ├── src/
  │   ├── main/          # Proceso principal de Electron (ciclo de vida, ventanas, IPC, tray)
  │   ├── preload/       # Bridge seguro entre Electron y la interfaz
  │   └── renderer/      # Assets, estilos personalizados o interfaz
  ├── config/            # Configuración de puertos y rutas al backend
  ├── package.json
  └── electron-builder.yml
  ```

### Fase 2: Conexión con el Backend / Datos de SSCP
- Implementar el conector/lanzador en Node.js/Electron para levantar el servicio local de SSCP o conectarse al puerto activo (con detección automática de puertos disponibles).
- Configurar copia de base de datos segura de prueba para no alterar los datos de producción de `sscp-desktop`.
- Integración de splash screen / pantalla de carga nativa con diseño médico profesional mientras se inicializan los servicios.

### Fase 3: Integración de Capacidades Nativas de Electron
- Menú de aplicación nativo con atajos de teclado (Ctrl+P para imprimir recetas, Ctrl+N para nueva consulta, F5 para recargar, pantalla completa F11).
- Manejo avanzado de descargas e impresión directa de recetas/informes PDF mediante las APIs nativas de Electron (`webContents.print`).
- Icono en la bandeja del sistema (System Tray) con opciones de abrir, minimizar y salir.
- Ventana frameless con barra de título personalizada moderna (opcional) o controles nativos de Windows 11.

### Fase 4: Pruebas y Verificación
- Prueba de arranque en frío (tiempo de carga inicial).
- Prueba de navegación entre módulos (Pacientes, Consultas, Citas, Laboratorios, Inventario).
- Prueba de generación y descarga de recetas en PDF.
- Comparativa visual y de rendimiento con la versión actual de `sscp-desktop`.

---

## ✅ Estado de Implementación (Enfoque A Completado)
* **Fase 1 (Inicialización)**: `package.json`, Electron v44 instalado, estructura de carpetas configurada.
* **Fase 2 (Orquestador Backend)**: `server-manager.js` con clonación segura de base de datos aislada, detección de puertos y monitoreo de salud.
* **Fase 3 (Capacidades Nativas)**: Menú nativo con atajos (`menu.js`), Splash screen con animación ECG (`splash.html`), Tray icon y gestión de procesos (zero-zombies en Windows).
* **Fase 4 (Verificación)**: Probado y verificado con `scripts/verify-backend.js`. Levantamiento de Uvicorn, conexión HTTP y apagado limpio comprobados con éxito.
* **Lanzador rápido**: Listo en `start.bat`.
