import sys
import os
import time
import webbrowser
import threading
from pathlib import Path

# Configurar encoding UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Determinar directorios según modo congelado (PyInstaller .exe) o desarrollo
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS).resolve()
    APP_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
    APP_DIR = BASE_DIR

# Asegurar que la carpeta 'data' exista en el directorio de la aplicación
data_dir = APP_DIR / "data"
data_dir.mkdir(parents=True, exist_ok=True)

def open_browser_delayed():
    """Abre el navegador automáticamente una vez que el servidor esté activo."""
    time.sleep(1.8)
    try:
        webbrowser.open("http://127.0.0.1:8080")
    except Exception as e:
        print(f"Aviso: No se pudo abrir automáticamente el navegador ({e}). Ingrese a http://127.0.0.1:8080")

def run():
    print("==================================================================")
    print(" 🏥  SSCP Desktop - Sistema de Seguimiento Clínico para Pacientes")
    print("     Servidor local activo en: http://127.0.0.1:8080")
    print("     Presione Ctrl+C en esta ventana para cerrar la aplicación.")
    print("==================================================================")

    # Iniciar navegador en segundo plano
    threading.Thread(target=open_browser_delayed, daemon=True).start()

    import uvicorn
    from main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8080,
        log_level="info",
        access_log=False
    )

if __name__ == "__main__":
    run()
