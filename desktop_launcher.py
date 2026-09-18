import sys
import os
import time
import socket
import threading
import webbrowser
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

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

def wait_for_server(host, port, timeout=12.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.15)
    return False

def run_server(server):
    try:
        server.run()
    except Exception:
        pass

def run():
    import uvicorn
    from main import app

    config = uvicorn.Config(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)

    # Iniciar servidor Uvicorn en hilo secundario daemon
    server_thread = threading.Thread(target=run_server, args=(server,), daemon=True)
    server_thread.start()

    # Esperar a que el servidor esté activo
    wait_for_server(SERVER_HOST, SERVER_PORT, timeout=10.0)

    # Intentar abrir con ventana nativa de escritorio (PyWebView)
    opened_native = False
    try:
        import webview

        icon_path = str(BASE_DIR / "static" / "app_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = None

        window = webview.create_window(
            title="SSCP Desktop - Sistema de Seguimiento Clínico para Pacientes",
            url=SERVER_URL,
            width=1280,
            height=820,
            min_size=(1000, 680),
            text_select=True,
            confirm_close=False,
        )

        opened_native = True
        # Iniciar loop GUI nativo de Windows (bloqueante en hilo principal)
        webview.start(private_mode=False, icon=icon_path)

    except Exception:
        opened_native = False

    if not opened_native:
        # Fallback a navegador predeterminado si pywebview no inicia
        try:
            webbrowser.open(SERVER_URL)
        except Exception:
            pass

        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    server.should_exit = True
    sys.exit(0)

if __name__ == "__main__":
    run()

