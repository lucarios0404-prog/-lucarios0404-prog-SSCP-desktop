import sys
import os
import time
import socket
import threading
import webbrowser
from pathlib import Path

# Flujo seguro de logging para modo sin consola
class LogStream:
    def __init__(self, file_path=None, fallback=None):
        self.file_path = file_path
        self.fallback = fallback

    def write(self, s):
        if not s:
            return
        if self.fallback and hasattr(self.fallback, "write"):
            try:
                self.fallback.write(s)
            except Exception:
                pass
        if self.file_path:
            try:
                with open(self.file_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(s)
            except Exception:
                pass

    def flush(self):
        if self.fallback and hasattr(self.fallback, "flush"):
            try:
                self.fallback.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def read(self, *args):
        return ""

    def readline(self, *args):
        return ""

# Determinar directorios según modo congelado (PyInstaller .exe) o desarrollo
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS).resolve()
    APP_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
    APP_DIR = BASE_DIR

# Determinar directorio de datos garantizando permisos de escritura en Windows
if os.environ.get("SSCP_DATA_DIR"):
    data_dir = Path(os.environ["SSCP_DATA_DIR"])
else:
    if getattr(sys, "frozen", False) and not (APP_DIR / "portable.flag").exists():
        local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local_app_data:
            data_dir = Path(local_app_data) / "SSCP" / "data"
        else:
            data_dir = Path.home() / "AppData" / "Local" / "SSCP" / "data"
    else:
        data_dir = APP_DIR / "data"

try:
    data_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Redirigir stdout y stderr a backend.log de forma segura
try:
    log_file_path = data_dir / "backend.log"
    sys.stdout = LogStream(log_file_path, sys.stdout)
    sys.stderr = LogStream(log_file_path, sys.stderr)
except Exception:
    pass

# Configurar encoding UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SERVER_HOST = os.environ.get("SSCP_HOST", "0.0.0.0")
CLIENT_HOST = "127.0.0.1"

def find_available_port(host, start_port=8080, max_attempts=20):
    """Encuentra un puerto disponible para prevenir colisiones de socket (Errno 10048)."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start_port

def wait_for_server(host, port, timeout=25.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.2)
    return False

def run_server(server):
    try:
        server.run()
    except Exception as e:
        try:
            log_path = data_dir / "backend.log"
            import traceback
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SERVER CRITICAL] {str(e)}\n{traceback.format_exc()}\n")
        except Exception:
            pass

def run():
    import uvicorn
    from main import app

    env_port = os.environ.get("SSCP_PORT")
    if env_port and env_port.isdigit():
        server_port = int(env_port)
    else:
        server_port = find_available_port(SERVER_HOST, 8080)
    server_url = f"http://{CLIENT_HOST}:{server_port}"

    config = uvicorn.Config(
        app,
        host=SERVER_HOST,
        port=server_port,
        log_config=None,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)

    # Iniciar servidor Uvicorn en hilo secundario daemon
    server_thread = threading.Thread(target=run_server, args=(server,), daemon=True)
    server_thread.start()

    # Esperar hasta 25 segundos a que el servidor esté activo antes de mostrar la UI
    server_ready = wait_for_server(CLIENT_HOST, server_port, timeout=25.0)
    if not server_ready:
        wait_for_server(CLIENT_HOST, server_port, timeout=5.0)

    # Si se pasa --server-only o --headless, servir en segundo plano para Electron sin abrir ventana GUI
    if "--server-only" in sys.argv or "--headless" in sys.argv:
        try:
            while server_thread.is_alive():
                time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            pass
        server.should_exit = True
        sys.exit(0)

    # Intentar abrir con ventana nativa de escritorio (PyWebView)
    opened_native = False
    try:
        import webview

        # Habilitar descargas de archivos (PDFs, CSV, backups) y enlaces externos en la ventana nativa
        try:
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.settings['ALLOW_FILE_URLS'] = True
            webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        except Exception:
            pass

        icon_path = str(BASE_DIR / "static" / "app_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = None

        window = webview.create_window(
            title="SSCP Desktop - Sistema de Seguimiento Clínico para Pacientes",
            url=server_url,
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
            webbrowser.open(server_url)
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

